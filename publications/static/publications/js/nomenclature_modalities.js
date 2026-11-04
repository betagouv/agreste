(function () {
  "use strict";

  function lockHeadings(node) {
    if (!(node instanceof Element)) {
      return;
    }
    var inputs = [];
    if (node.matches("input.column-heading") && node.closest(".nomenclature-modalities")) {
      inputs.push(node);
    }
    node.querySelectorAll(".nomenclature-modalities input.column-heading").forEach(function (input) {
      inputs.push(input);
    });
    inputs.forEach(function (input) {
      input.readOnly = true;
      input.tabIndex = -1;
    });
  }

  function start() {
    lockHeadings(document.body);
    var observer = new MutationObserver(function (records) {
      records.forEach(function (record) {
        record.addedNodes.forEach(lockHeadings);
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
