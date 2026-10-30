from wagtail.api.v2.filters import FieldsFilter, LocaleFilter, OrderingFilter
from wagtail.api.v2.views import BaseAPIViewSet

from publications.models import Collection, GeographicLevel, ReferenceYear, StatisticalSource, Theme


class CollectionsAPIViewSet(BaseAPIViewSet):
    model = Collection
    filter_backends = [FieldsFilter, LocaleFilter, OrderingFilter]
    listing_default_fields = BaseAPIViewSet.listing_default_fields + ["name", "slug"]


class ThemesAPIViewSet(BaseAPIViewSet):
    model = Theme
    filter_backends = [FieldsFilter, LocaleFilter, OrderingFilter]
    listing_default_fields = BaseAPIViewSet.listing_default_fields + ["name", "slug"]


class StatisticalSourcesAPIViewSet(BaseAPIViewSet):
    model = StatisticalSource
    filter_backends = [FieldsFilter, LocaleFilter, OrderingFilter]
    listing_default_fields = BaseAPIViewSet.listing_default_fields + ["name", "slug"]


class ReferenceYearsAPIViewSet(BaseAPIViewSet):
    model = ReferenceYear
    filter_backends = [FieldsFilter, LocaleFilter, OrderingFilter]
    listing_default_fields = BaseAPIViewSet.listing_default_fields + ["name", "slug"]


class GeographicLevelsAPIViewSet(BaseAPIViewSet):
    model = GeographicLevel
    filter_backends = [FieldsFilter, LocaleFilter, OrderingFilter]
    listing_default_fields = BaseAPIViewSet.listing_default_fields + ["name", "slug"]
