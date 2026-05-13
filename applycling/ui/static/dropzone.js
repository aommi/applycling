(function () {
  "use strict";

  function describeFile(file) {
    var sizeKb = Math.max(1, Math.round(file.size / 1024));
    return file.name + " (" + sizeKb + " KB)";
  }

  function showSelected(zone, hint, file) {
    zone.classList.add("has-file");
    hint.innerHTML = "";
    var title = document.createElement("span");
    title.className = "dropzone-title";
    title.textContent = describeFile(file);
    var sub = document.createElement("span");
    sub.className = "dropzone-sub";
    sub.textContent = "Click or drop another file to replace";
    hint.appendChild(title);
    hint.appendChild(sub);
  }

  function init(zone) {
    var input = zone.querySelector("[data-dropzone-input]");
    var hint = zone.querySelector("[data-dropzone-hint]");
    if (!input || !hint) return;

    ["dragenter", "dragover"].forEach(function (evt) {
      zone.addEventListener(evt, function (e) {
        e.preventDefault();
        e.stopPropagation();
        zone.classList.add("is-dragover");
      });
    });

    ["dragleave", "dragend"].forEach(function (evt) {
      zone.addEventListener(evt, function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (evt === "dragleave" && zone.contains(e.relatedTarget)) return;
        zone.classList.remove("is-dragover");
      });
    });

    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      e.stopPropagation();
      zone.classList.remove("is-dragover");
      var files = e.dataTransfer && e.dataTransfer.files;
      if (!files || files.length === 0) return;
      try {
        var dt = new DataTransfer();
        dt.items.add(files[0]);
        input.files = dt.files;
      } catch (err) {
        return;
      }
      showSelected(zone, hint, files[0]);
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });

    input.addEventListener("change", function () {
      if (input.files && input.files.length > 0) {
        showSelected(zone, hint, input.files[0]);
      }
    });
  }

  document.querySelectorAll("[data-dropzone]").forEach(init);
})();
