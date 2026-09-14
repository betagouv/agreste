from django.test import SimpleTestCase

from publications.blocks.publication_subtitle import PublicationSubtitleBlock


class PublicationSubtitleBlockTestCase(SimpleTestCase):
    def test_renders_subtitle_as_h2(self):
        block = PublicationSubtitleBlock()
        value = block.to_python({"subtitle": "Section title"})
        html = block.render(value)

        self.assertIn("Section title", html)
        self.assertIn("<h2>", html)
