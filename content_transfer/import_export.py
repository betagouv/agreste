"""
Import and export of pages, images and documents between Wagtail instances, through the API (`api/v2/`).

Only ``ContentPage`` is supported: every transferred page is created or updated as a
``sites_conformes_core.ContentPage``. The source ``meta.type`` is ignored; other page
types (for example ``PublicationPage``) are not preserved.

Publications blocks registered on ``ContentPage.body``
(``downloadable_document``, ``standard_publication``, ``freeform_publication``,
``publication_recent_entries``, …) use the same nested StreamField keys
(``document``, ``image`` / ``bg_image``, ``page`` / ``index_page``, rich-text
``linktype``) and are covered by the recursive image, page and document walkers.

Example::

    python manage.py transfer_pages --ids 5 7 --site_url https://source.example.com/ --parent_page_slug donnees
"""

import copy
import json
import os
import re
import sys
from io import BytesIO
from pathlib import Path, PosixPath

import requests
import swapper
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import File
from django.core.files.images import ImageFile
from django.utils import timezone
from wagtail.documents import get_document_model
from wagtail.images import get_image_model
from wagtail.models import Page
from wagtail.utils.file import hash_filelike

from sites_conformes.core.constants import HEADER_FIELDS
from sites_conformes.core.services.accessors import get_or_create_collection, get_or_create_content_page
from sites_conformes.core.utils import get_default_site

ContentPage = swapper.load_model("sites_conformes_core", "ContentPage")

PAGE_TEMPLATES_ROOT = settings.BASE_DIR / "sites_conformes/core/page_templates"
TEMPLATES_DATA_FILE = PAGE_TEMPLATES_ROOT / "pages_data.json"
IMAGES_FOLDER = PAGE_TEMPLATES_ROOT / "img"
DOCUMENTS_FOLDER = PAGE_TEMPLATES_ROOT / "docs"

# PageChooser field names used in Sites Conformes StreamField blocks
PAGE_CHOOSER_KEYS = frozenset({"page", "blog", "index_page"})
PAGE_LINK_RICHTEXT_RE = re.compile(r'(linktype="page" id=")(\d+)(")')
DOCUMENT_LINK_RICHTEXT_RE = re.compile(r'(linktype="document" id=")(\d+)(")')

User = get_user_model()
Image = get_image_model()
Document = get_document_model()


class DocumentTransferError(Exception):
    """Raised when a document cannot be safely matched or imported on the destination."""


class ExportPage:
    """
    Generic class for export of a ContentPage from a wagtail instance

    The page is fetched from the API of `source_site` (a base URL ending with a slash)
    when the class is instantiated. The block IDs, the tags, the rendered header images
    and some meta keys are removed, and the IDs of the images and documents used by the
    page are listed in `image_ids` / `document_ids` for export with `ImportExportImages`
    and `ImportExportDocuments`.
    """

    def __init__(self, source_page_id, source_site) -> None:
        self.source_site = source_site
        self.source_page_id = source_page_id
        self.source_content = self.get_content_from_source_page()
        self.source_body = self.source_content["body"]
        self.user = User.objects.filter(is_superuser=True).first()

        self.content = copy.deepcopy(self.source_content)
        self.content["body"] = remove_block_ids(self.source_body)
        self.content.pop("tags", None)
        self.content.pop("header_image_render", None)
        self.content.pop("header_image_thumbnail", None)
        self.clear_meta_keys()

        self.images = {}
        self.image_ids = []
        self.document_ids = []
        self.get_source_images()
        self.get_source_documents()

    @property
    def json_export(self) -> dict:
        """
        The cleaned page content, ready to be imported with `ImportPages`.
        """
        return self.content

    @property
    def source_page_api_url(self):
        """
        The URL of the page in the API of the source site.
        """
        return f"{self.source_site}api/v2/pages/{self.source_page_id}/"

    def get_content_from_source_page(self):
        """
        Fetch the page from the API of the source site and return its JSON content.
        """
        response = requests.get(self.source_page_api_url, timeout=5)
        return response.json()

    def get_source_images(self) -> None:
        """
        Get a list of images present in the source content.

        Fills `image_ids` with the IDs of the header image and of the images of the body,
        without duplicates.
        """

        # Header image
        header_image = self.source_content.get("header_image", None)
        if header_image:
            header_image["local_image"] = None
            self.image_ids.append(header_image["id"])
            self.content["header_image"]["meta"].pop("download_url")

        # Images from the body
        self.locate_image_ids(self.source_body)
        self.image_ids = list(set(self.image_ids))

    def locate_image_ids(self, json_object):  # NOSONAR
        """
        Recursively walk a StreamField JSON representation and add to `image_ids`
        the values of the `image` and `bg_image` keys.

        An empty ImageBlock is a dict whose `image` id is null. That id is skipped,
        so the export does not request `/api/v2/images/None/`.
        """
        if isinstance(json_object, dict) and json_object:
            for key, value in json_object.items():
                if key in ["image", "bg_image"] and value:
                    # An ImageBlock is a dict of image id, alt text and decorative flag.
                    # The id is null when the block has no image chosen.
                    image_id = value.get("image") if isinstance(value, dict) else value
                    if image_id:
                        self.image_ids.append(image_id)
                else:
                    self.locate_image_ids(value)

        elif isinstance(json_object, list) and json_object:
            for item in json_object:
                self.locate_image_ids(item)

    def get_source_documents(self) -> None:
        """
        Collect document IDs from the body and header CTA buttons, without duplicates.
        """
        found: set[int] = set()
        locate_document_ids(self.source_body, found)
        locate_document_ids(self.source_content.get("header_cta_buttons"), found)
        self.document_ids = list(found)

    def clear_meta_keys(self):
        """
        Remove the meta keys that should not be copied to the imported page.
        """
        keys = ["parent", "seo_title", "search_description"]
        for key in keys:
            self.content["meta"].pop(key, None)


class ImportPages:
    """
    Generic class for import of a list of ContentPages from a previously made export

    `pages_data` is a dict with a `pages` key (the exported pages, by source page ID)
    and `image_ids` / `document_ids` keys. It defaults to the content of `TEMPLATES_DATA_FILE`.
    The pages are imported under the page whose slug is `parent_page_slug`, or under
    a page templates index created right under the Root page.
    """

    def __init__(
        self,
        pages_data: dict | None = None,
        parent_page_slug: str | None = None,
        image_folder: PosixPath | None = IMAGES_FOLDER,
        document_folder: PosixPath | None = DOCUMENTS_FOLDER,
    ) -> None:
        if pages_data is None:
            with open(TEMPLATES_DATA_FILE, "r") as json_file:
                pages_data = json.load(json_file)

        self.pages = pages_data["pages"]  # type: ignore
        self.image_ids = pages_data["image_ids"]  # type: ignore
        self.document_ids = pages_data.get("document_ids", [])  # type: ignore

        self.image_importer = ImportExportImages(self.image_ids, image_folder=image_folder)
        self.document_importer = ImportExportDocuments(self.document_ids, document_folder=document_folder)

        if parent_page_slug:
            self.parent_page = ContentPage.objects.get(slug=parent_page_slug)
        else:
            # Do not create the parent page at this step if it doesn't exit
            self.parent_page = None

    def get_or_create_page_templates_index(self) -> ContentPage:
        """
        Get or create the page templates index, used as parent page when none is given.
        """
        # The templates index is created right under the Root page, like a site
        parent_page = Page.objects.first()
        body = [("subpageslist", None)]
        return get_or_create_content_page(
            slug="page_templates_index", title="Modèles de pages à copier", body=body, parent_page=parent_page
        )

    def import_pages(self) -> list[ContentPage]:
        """
        Import the images and documents, then the pages.

        A page that was already imported under the parent page (same `source_url`)
        is updated instead of being duplicated.

        Returns the created or updated pages, in the order of the export.
        """
        self.image_importer.import_images()
        self.document_importer.import_documents()

        if not self.parent_page:
            self.parent_page = self.get_or_create_page_templates_index()

        self.transferred_pages: dict[str, ContentPage] = {}
        for page_id in self.pages.keys():
            self.update_image_ids(page_id)
            self.update_document_ids(page_id)

            raw_page = self.pages[page_id]
            source_url = raw_page["meta"]["html_url"]

            page_exists = ContentPage.objects.child_of(self.parent_page).filter(source_url=source_url).first()
            if page_exists:
                page = self.update_page(page_id, page_exists)
            else:
                page = self.import_page(page_id)
            self.transferred_pages[str(page_id)] = page

        return list(self.transferred_pages.values())

    def fix_page_links(self, source_site: str) -> None:
        """
        Replace source page IDs in transferred page bodies with local page IDs.

        Matching is by slug: source page id → source slug → local page pk.
        """
        if not getattr(self, "transferred_pages", None):
            return

        source_id_to_slug = {str(source_id): raw_page["meta"]["slug"] for source_id, raw_page in self.pages.items()}

        referenced_ids: set[int] = set()
        for raw_page in self.pages.values():
            locate_page_ids(raw_page.get("body"), referenced_ids)
            locate_page_ids(raw_page.get("header_cta_buttons"), referenced_ids)

        for page_id in referenced_ids:
            page_id_str = str(page_id)
            if page_id_str in source_id_to_slug:
                continue
            slug = self.fetch_source_page_slug(source_site, page_id)
            if slug:
                source_id_to_slug[page_id_str] = slug

        page_id_map = {}
        for source_id, slug in source_id_to_slug.items():
            local_pk = self.local_page_pk_for_slug(slug)
            if local_pk is not None:
                page_id_map[source_id] = local_pk

        for source_id, page in self.transferred_pages.items():
            raw_page = self.pages.get(source_id)
            if raw_page is None and source_id.isdigit():
                raw_page = self.pages.get(int(source_id))
            raw_page["body"] = update_streamfield_page_ids(raw_page["body"], page_id_map)
            if raw_page.get("header_cta_buttons"):
                raw_page["header_cta_buttons"] = update_streamfield_page_ids(
                    raw_page["header_cta_buttons"], page_id_map
                )
            page.body = raw_page["body"]
            if "header_cta_buttons" in raw_page and raw_page["header_cta_buttons"] is not None:
                page.header_cta_buttons = raw_page["header_cta_buttons"]
            page.save()
            sys.stdout.write(f"Page links updated on {page.slug}.\n")

    def fetch_source_page_slug(self, source_site: str, page_id: int) -> str | None:
        """
        Fetch a page from the source API and return its slug, or None on failure.
        """
        url = f"{source_site}api/v2/pages/{page_id}/"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return response.json()["meta"]["slug"]
        except (requests.RequestException, KeyError, TypeError, ValueError):
            sys.stdout.write(f"Could not resolve source page {page_id} to a slug.\n")
            return None

    def local_page_pk_for_slug(self, slug: str) -> int | None:
        """
        Return the local page pk for ``slug``, preferring a child of the import parent.
        """
        if self.parent_page:
            under_parent = Page.objects.child_of(self.parent_page).filter(slug=slug).first()
            if under_parent:
                return under_parent.pk

        locale = get_default_site().root_page.locale
        page = Page.objects.filter(slug=slug, locale=locale).first()
        return page.pk if page else None

    def import_page(self, page_id: str) -> ContentPage:
        """
        Create a new page from the exported page with the given source ID.
        """
        raw_page = self.pages[page_id]
        source_url = raw_page["meta"]["html_url"]

        page_dict = {
            "slug": raw_page["meta"]["slug"],
            "title": raw_page["title"],
            "body": raw_page["body"],
            "parent_page": self.parent_page,
        }

        page_fields = {"source_url": source_url}

        for field in HEADER_FIELDS:
            if raw_page[field]:
                page_fields[field] = raw_page[field]
        page_dict["page_fields"] = page_fields
        return get_or_create_content_page(**page_dict)

    def update_page(self, source_page_id, existing_page):
        """
        Update an existing page (slug, title, body and header fields)
        with the content of the exported page with the given source ID.
        """
        raw_page = self.pages[source_page_id]
        existing_page.slug = raw_page["meta"]["slug"]
        existing_page.title = raw_page["title"]
        existing_page.body = raw_page["body"]

        for field in HEADER_FIELDS:
            if raw_page[field]:
                setattr(existing_page, field, raw_page[field])

        existing_page.save()
        sys.stdout.write(f"Page {existing_page.slug} has been updated.\n")
        return existing_page

    def update_image_ids(self, page_id):
        """
        Replace the source image IDs of the exported page with the IDs of the imported images.
        """
        page = self.pages[page_id]

        if page["header_image"]:
            source_image_id = str(page["header_image"]["id"])
            local_image_id = self.image_importer.image_data[source_image_id]["local_id"]

            # We need to replace the dictionary with the image itself
            page["header_image"] = Image.objects.get(pk=local_image_id)

        page["body"] = update_streamfield_image_ids(page["body"], self.image_importer.image_data)

    def update_document_ids(self, page_id):
        """
        Replace the source document IDs of the exported page with the IDs of the imported documents.
        """
        page = self.pages[page_id]
        document_data = self.document_importer.document_data
        page["body"] = update_streamfield_document_ids(page["body"], document_data)
        if page.get("header_cta_buttons"):
            page["header_cta_buttons"] = update_streamfield_document_ids(page["header_cta_buttons"], document_data)


class ImportExportImages:
    """
    Generic class for import/export of a list of Images from a wagtail instance

    `image_folder` holds the image files and an `image_data.json` file with their metadata.
    `source_site` (a base URL ending with a slash) is only needed to download images.

    When instantiated, the class creates `image_folder` and the
    "Images des modèles de page" collection if they don't exist.
    """

    def __init__(self, image_ids, source_site=None, image_folder: PosixPath | None = IMAGES_FOLDER) -> None:
        self.user = User.objects.filter(is_superuser=True).first()

        self.image_ids = set(image_ids)
        self.source_site = source_site

        # Create the folder for the files if it doesn't exist
        self.image_folder = image_folder
        os.makedirs(image_folder, exist_ok=True)

        self.image_data_file = self.image_folder / "image_data.json"  # type: ignore

        # Create the collection if it doesn't exit
        self.collection = get_or_create_collection("Images des modèles de page")

        self.image_data = self.get_image_data()

    def get_image_data(self) -> dict:
        """
        Return the content of `image_data.json`, or an empty dict if the file doesn't exist.
        """
        if os.path.isfile(self.image_data_file):
            with open(self.image_data_file, "r") as json_file:
                image_data = json.load(json_file)
        else:
            image_data = {}

        return image_data

    def source_image_api_url(self, image_id: int) -> str:
        """
        Return the URL of the image in the API of the source site.
        """
        return f"{self.source_site}api/v2/images/{image_id}/"

    def get_content_from_source_image(self, image_id: int) -> dict:
        """
        Fetch the image from the API of the source site and return its JSON content.
        """
        response = requests.get(self.source_image_api_url(image_id), timeout=5)
        return response.json()

    def download_images(self) -> None:
        """
        Download the images from the source site to `image_folder`, and save their metadata
        in `image_data.json`.

        The DSFR pictograms are not downloaded, as they should already be present
        on the target site: they are found again by their title when imported.
        """
        for i in self.image_ids:
            i = str(i)
            image = self.get_content_from_source_image(i)

            if i not in self.image_data:
                self.image_data[i] = {}
            self.image_data[i]["meta"] = image["meta"]
            self.image_data[i]["title"] = image["title"]

            image_url = image["meta"].pop("download_url")
            image_name = image_url.split("?")[0].split("/")[-1]

            # No need to export the pictograms, as they should already be present
            if "Pictogrammes_DSFR" in image_name:
                pictogram_title = image_name.replace("__", " — ").replace("_", " ")
                self.image_data[i]["filename"] = pictogram_title
                self.image_data[i]["is_pictogram"] = True

            else:
                with requests.get(image_url, timeout=5, stream=True) as image_response:
                    image_response.raise_for_status()
                    with open(self.image_folder / image_name, "wb") as image_file:
                        for chunk in image_response.iter_content(chunk_size=8192):
                            image_file.write(chunk)
                self.image_data[i]["filename"] = image_name
                self.image_data[i]["is_pictogram"] = False

        with open(self.image_data_file, "w") as json_file:
            json.dump(self.image_data, json_file, indent=2)
            json_file.write("\n")

    def import_images(self) -> None:
        """
        Import the images from `image_folder`, and store the ID of each local image
        in the `local_id` key of its entry in `image_data`.
        """
        for i in self.image_ids:
            i = str(i)
            image_data = self.image_data[i]
            filename = image_data["filename"]

            if image_data["is_pictogram"]:
                pictogram = Image.objects.filter(title=filename).first()
                image_data["local_id"] = pictogram.id
            else:
                image = self.get_or_create_image(image_data)
                image_data["local_id"] = image.id

    def get_or_create_image(self, image_data) -> Image:
        """
        Return the local image with the same file hash, or create it from the file in `image_folder`.
        """
        filename = image_data["filename"]
        imported_filename = f"template_image_{filename.lower()}"
        title = image_data["title"]

        with open(self.image_folder / filename, "rb") as image_file:
            file_hash = hash_filelike(image_file)

            image = Image.objects.filter(file_hash=file_hash).first()
            if not image:
                image = Image(
                    file=ImageFile(BytesIO(image_file.read()), name=imported_filename),
                    title=title,
                    uploaded_by_user=self.user,
                    collection=self.collection,
                    created_at=timezone.now(),
                )
                image.save()
                image.get_file_hash()

        return image


class ImportExportDocuments:
    """
    Import/export of Documents from a Wagtail instance via the documents API.

    `document_folder` holds the files and a `document_data.json` metadata file.
    `source_site` is only needed to download documents.

    Local reuse requires a unique match on title, filename basename, and file_hash.
    """

    def __init__(self, document_ids, source_site=None, document_folder: PosixPath | None = DOCUMENTS_FOLDER) -> None:
        self.user = User.objects.filter(is_superuser=True).first()

        self.document_ids = set(document_ids)
        self.source_site = source_site

        self.document_folder = document_folder
        os.makedirs(document_folder, exist_ok=True)

        self.document_data_file = self.document_folder / "document_data.json"  # type: ignore

        self.collection = get_or_create_collection("Documents des modèles de page")

        self.document_data = self.get_document_data()

    def get_document_data(self) -> dict:
        """
        Return the content of `document_data.json`, or an empty dict if the file doesn't exist.
        """
        if os.path.isfile(self.document_data_file):
            with open(self.document_data_file, "r") as json_file:
                return json.load(json_file)
        return {}

    def source_document_api_url(self, document_id: int | str) -> str:
        """
        Return the URL of the document in the API of the source site.
        """
        return f"{self.source_site}api/v2/documents/{document_id}/"

    def get_content_from_source_document(self, document_id: int | str) -> dict:
        """
        Fetch the document from the API of the source site and return its JSON content.
        """
        response = requests.get(self.source_document_api_url(document_id), timeout=5)
        response.raise_for_status()
        return response.json()

    def download_documents(self) -> None:
        """
        Download documents from the source site to `document_folder`, and save metadata
        in `document_data.json`.
        """
        for document_id in self.document_ids:
            document_id = str(document_id)
            document = self.get_content_from_source_document(document_id)

            if document_id not in self.document_data:
                self.document_data[document_id] = {}
            self.document_data[document_id]["meta"] = document["meta"]
            self.document_data[document_id]["title"] = document["title"]

            document_url = document["meta"].pop("download_url")
            document_name = document_url.split("?")[0].split("/")[-1]

            with requests.get(document_url, timeout=5, stream=True) as document_response:
                document_response.raise_for_status()
                with open(self.document_folder / document_name, "wb") as document_file:
                    for chunk in document_response.iter_content(chunk_size=8192):
                        document_file.write(chunk)

            self.document_data[document_id]["filename"] = document_name

        with open(self.document_data_file, "w") as json_file:
            json.dump(self.document_data, json_file, indent=2)
            json_file.write("\n")

    def import_documents(self) -> None:
        """
        Resolve or create each document and store its local ID in `document_data`.
        """
        for document_id in self.document_ids:
            document_id = str(document_id)
            document_data = self.document_data[document_id]
            document = self.resolve_or_create_document(document_id, document_data)
            document_data["local_id"] = document.id

    def resolve_or_create_document(self, source_id: str, document_data: dict) -> Document:
        """
        Reuse a local document matching title, filename and hash, or create one.

        Raises ``DocumentTransferError`` on ambiguous or partial name matches.
        """
        filename = document_data["filename"]
        title = document_data["title"]
        path = self.document_folder / filename

        with open(path, "rb") as document_file:
            file_hash = hash_filelike(document_file)

        name_hits = self.find_documents_by_title_or_filename(title, filename)
        full_hits = [
            doc
            for doc in name_hits
            if doc.title == title and Path(doc.file.name).name == filename and doc.file_hash == file_hash
        ]

        if len(full_hits) == 1 and len(name_hits) == 1:
            existing = full_hits[0]
            sys.stdout.write(
                f"Document already present: source id {source_id} "
                f"(title={title!r}, filename={filename!r}) → local id {existing.pk}.\n"
            )
            return existing

        if len(full_hits) > 1:
            raise DocumentTransferError(
                f"Ambiguous document match for source id {source_id} "
                f"(title={title!r}, filename={filename!r}, hash={file_hash}): "
                f"{len(full_hits)} local documents match title, filename and hash."
            )

        if name_hits:
            raise DocumentTransferError(
                f"Conflicting document on destination for source id {source_id} "
                f"(title={title!r}, filename={filename!r}, hash={file_hash}): "
                f"found {len(name_hits)} document(s) with the same title or filename "
                f"but not a unique title+filename+hash match."
            )

        document = self.create_document(document_data)
        sys.stdout.write(
            f"Document created: source id {source_id} "
            f"(title={title!r}, filename={filename!r}) → local id {document.pk}.\n"
        )
        return document

    def find_documents_by_title_or_filename(self, title: str, filename: str) -> list:
        """
        Return local documents whose title equals ``title`` or whose file basename equals ``filename``.
        """
        by_title = list(Document.objects.filter(title=title))
        by_filename = [
            doc
            for doc in Document.objects.filter(file__endswith=filename)
            if Path(doc.file.name).name == filename and doc not in by_title
        ]
        return by_title + by_filename

    def create_document(self, document_data: dict) -> Document:
        """
        Create a local Document from the file in `document_folder`.

        The original basename is kept so a later transfer can match title + filename + hash.
        ``_set_document_file_metadata`` fills ``file_size`` and ``file_hash`` (same as
        ``create_publications._create_wagtail_document``).
        """
        filename = document_data["filename"]
        title = document_data["title"]

        with open(self.document_folder / filename, "rb") as document_file:
            document = Document(
                title=title,
                file=File(BytesIO(document_file.read()), name=filename),
                uploaded_by_user=self.user,
                collection=self.collection,
            )
            document._set_document_file_metadata()
            document.save()

        return document


def remove_block_ids(json_object):
    """
    Parse a page JSON StreamField representation and strip the block IDs

    Returns a new structure, the original one is not modified.
    """
    if not isinstance(json_object, (dict, list)):
        return json_object
    if isinstance(json_object, list):
        return [remove_block_ids(v) for v in json_object]
    return {k: remove_block_ids(v) for k, v in json_object.items() if k != "id"}


def update_streamfield_image_ids(json_object, image_ids):
    """
    Parse a page JSON StreamField representation and update the image IDs

    `image_ids` maps the source image IDs (as strings) to dicts holding the local ID
    in their `local_id` key, such as `ImportExportImages.image_data`.
    The dicts are updated in place; the updated structure is also returned.
    """
    if isinstance(json_object, dict):
        for k, v in json_object.items():
            v_str = str(v)
            if k in ["image", "bg_image"] and v_str in image_ids:
                json_object[k] = image_ids[v_str]["local_id"]
            else:
                update_streamfield_image_ids(v, image_ids)
    elif isinstance(json_object, list):
        return [update_streamfield_image_ids(v, image_ids) for v in json_object]
    return json_object


def locate_page_ids(json_object, found: set[int] | None = None) -> set[int]:
    """
    Recursively collect page IDs from PageChooser fields and rich-text page links.
    """
    if found is None:
        found = set()

    if isinstance(json_object, dict):
        for key, value in json_object.items():
            if key in PAGE_CHOOSER_KEYS and isinstance(value, int):
                found.add(value)
            elif key in PAGE_CHOOSER_KEYS and isinstance(value, str) and value.isdigit():
                found.add(int(value))
            else:
                locate_page_ids(value, found)
    elif isinstance(json_object, list):
        for item in json_object:
            locate_page_ids(item, found)
    elif isinstance(json_object, str):
        for match in PAGE_LINK_RICHTEXT_RE.finditer(json_object):
            found.add(int(match.group(2)))

    return found


def locate_document_ids(json_object, found: set[int] | None = None) -> set[int]:
    """
    Recursively collect document IDs from DocumentChooser fields and rich-text document links.
    """
    if found is None:
        found = set()

    if isinstance(json_object, dict):
        for key, value in json_object.items():
            if key == "document" and isinstance(value, int):
                found.add(value)
            elif key == "document" and isinstance(value, str) and value.isdigit():
                found.add(int(value))
            else:
                locate_document_ids(value, found)
    elif isinstance(json_object, list):
        for item in json_object:
            locate_document_ids(item, found)
    elif isinstance(json_object, str):
        for match in DOCUMENT_LINK_RICHTEXT_RE.finditer(json_object):
            found.add(int(match.group(2)))

    return found


def update_streamfield_page_ids(json_object, page_id_map: dict):
    """
    Replace source page IDs with local IDs in a StreamField JSON representation.

    ``page_id_map`` maps source page IDs (as strings) to local page pks.
    Unknown IDs are left unchanged. The structure is updated in place and returned.
    """
    if isinstance(json_object, dict):
        for key, value in json_object.items():
            if key in PAGE_CHOOSER_KEYS and value is not None:
                value_str = str(value)
                if value_str in page_id_map:
                    json_object[key] = page_id_map[value_str]
                else:
                    json_object[key] = update_streamfield_page_ids(value, page_id_map)
            else:
                json_object[key] = update_streamfield_page_ids(value, page_id_map)
    elif isinstance(json_object, list):
        for index, item in enumerate(json_object):
            json_object[index] = update_streamfield_page_ids(item, page_id_map)
    elif isinstance(json_object, str):

        def replace_richtext_id(match):
            source_id = match.group(2)
            if source_id in page_id_map:
                return f"{match.group(1)}{page_id_map[source_id]}{match.group(3)}"
            return match.group(0)

        return PAGE_LINK_RICHTEXT_RE.sub(replace_richtext_id, json_object)
    return json_object


def update_streamfield_document_ids(json_object, document_ids):
    """
    Replace source document IDs with local IDs in a StreamField JSON representation.

    ``document_ids`` maps source document IDs (as strings) to dicts holding the local ID
    in their ``local_id`` key, such as ``ImportExportDocuments.document_data``.
    Unknown IDs are left unchanged. The structure is updated in place and returned.
    """
    if isinstance(json_object, dict):
        for key, value in json_object.items():
            if key == "document" and value is not None:
                value_str = str(value)
                if value_str in document_ids:
                    json_object[key] = document_ids[value_str]["local_id"]
                else:
                    json_object[key] = update_streamfield_document_ids(value, document_ids)
            else:
                json_object[key] = update_streamfield_document_ids(value, document_ids)
    elif isinstance(json_object, list):
        for index, item in enumerate(json_object):
            json_object[index] = update_streamfield_document_ids(item, document_ids)
    elif isinstance(json_object, str):

        def replace_richtext_id(match):
            source_id = match.group(2)
            if source_id in document_ids:
                return f"{match.group(1)}{document_ids[source_id]['local_id']}{match.group(3)}"
            return match.group(0)

        return DOCUMENT_LINK_RICHTEXT_RE.sub(replace_richtext_id, json_object)
    return json_object
