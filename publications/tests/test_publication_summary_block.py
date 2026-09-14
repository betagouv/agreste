from django.test import SimpleTestCase

from publications.blocks.publication_summary import PublicationSummaryBlock


class PublicationSummaryBlockTestCase(SimpleTestCase):
    def test_renders_summary_richtext(self):
        block = PublicationSummaryBlock()
        value = block.to_python({"summary": "<p>Summary text</p>"})
        html = block.render(value)

        self.assertIn("Summary text", html)
        self.assertIn("<p>", html)
