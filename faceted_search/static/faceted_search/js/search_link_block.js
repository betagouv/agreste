(function () {
  var Original = window.telepath.constructors["blocks.links.LinkBlock"];
  if (!Original) {
    return;
  }

  var searchFieldNames = ["q", "collection", "theme", "date_from", "date_to", "rank_by"];

  class SearchAwareLinkBlockDefinition extends Original {
    render(placeholder, prefix, initialState, initialError) {
      const block = super.render(placeholder, prefix, initialState, initialError);
      const container = block.container[0];
      const select = container.querySelector('[data-contentpath="link_type"] select');
      const searchFields = searchFieldNames
        .map(function (name) {
          return container.querySelector('[data-contentpath="' + name + '"]');
        })
        .filter(Boolean);
      if (!select || searchFields.length === 0) {
        return block;
      }

      const update = function () {
        const show = select.value === "search";
        searchFields.forEach(function (field) {
          field.style.display = show ? "block" : "none";
        });
      };
      update();
      select.addEventListener("change", update);
      return block;
    }
  }

  window.telepath.register("blocks.links.LinkBlock", SearchAwareLinkBlockDefinition);
})();
