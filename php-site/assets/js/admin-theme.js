(function () {
  "use strict";

  var editor = document.getElementById("themeEditor");
  if (!editor) return;

  var presets = {
    classic: {
      color_cream: "#faf7f2", color_cream_deep: "#f3ede3",
      color_sage: "#6f8f7f", color_sage_dark: "#4f6f60", color_sage_light: "#e7efe9",
      color_terracotta: "#c98a6b", color_terracotta_dark: "#b5734f",
      color_ink: "#2c322f", color_ink_soft: "#5b635e"
    },
    warm: {
      color_cream: "#fbf6f0", color_cream_deep: "#f0e4d6",
      color_sage: "#8a7b6a", color_sage_dark: "#6d5f50", color_sage_light: "#ece4da",
      color_terracotta: "#c97d5d", color_terracotta_dark: "#a86448",
      color_ink: "#3a322c", color_ink_soft: "#6a625a"
    },
    fresh: {
      color_cream: "#f7faf8", color_cream_deep: "#e8f0eb",
      color_sage: "#5d8f7a", color_sage_dark: "#3f6f5c", color_sage_light: "#dcebe4",
      color_terracotta: "#7fa88e", color_terracotta_dark: "#5f8870",
      color_ink: "#243029", color_ink_soft: "#55635a"
    },
    contrast: {
      color_cream: "#ffffff", color_cream_deep: "#eef1ef",
      color_sage: "#2f5d4a", color_sage_dark: "#1f4033", color_sage_light: "#d9e8e0",
      color_terracotta: "#b85c3c", color_terracotta_dark: "#94482e",
      color_ink: "#111816", color_ink_soft: "#4a5550"
    }
  };

  function cssKey(name) {
    return "--" + name.replace("color_", "").replace(/_/g, "-");
  }

  function applyVars() {
    var root = document.documentElement;
    editor.querySelectorAll(".theme-color-row").forEach(function (row) {
      var key = row.getAttribute("data-color-key");
      var pick = row.querySelector(".theme-pick");
      if (key && pick && pick.value) {
        root.style.setProperty(cssKey(key), pick.value);
      }
    });
    updatePreview();
  }

  function updatePreview() {
    var get = function (k) {
      var el = editor.querySelector('[name="' + k + '"]');
      return el ? el.value : "";
    };
    var chips = document.getElementById("themePreview");
    if (!chips) return;
    chips.querySelector('[data-chip="cream"]').style.background = get("color_cream");
    chips.querySelector('[data-chip="sage"]').style.background = get("color_sage");
    chips.querySelector('[data-chip="terracotta"]').style.background = get("color_terracotta");
    var ink = chips.querySelector('[data-chip="ink"]');
    ink.style.color = get("color_ink");
    ink.style.borderColor = get("color_sage");
  }

  function setColor(key, value) {
    var row = editor.querySelector('[data-color-key="' + key + '"]');
    if (!row) return;
    var pick = row.querySelector(".theme-pick");
    var hex = row.querySelector(".theme-hex");
    if (pick) pick.value = value;
    if (hex) hex.value = value;
  }

  editor.querySelectorAll(".theme-color-row").forEach(function (row) {
    var pick = row.querySelector(".theme-pick");
    var hex = row.querySelector(".theme-hex");
    if (!pick || !hex) return;
    pick.addEventListener("input", function () {
      hex.value = pick.value;
      applyVars();
    });
    hex.addEventListener("input", function () {
      var v = hex.value.trim();
      if (/^#[0-9a-fA-F]{6}$/.test(v)) {
        pick.value = v;
        applyVars();
      }
    });
    hex.addEventListener("blur", function () {
      var v = hex.value.trim();
      if (!/^#/.test(v)) v = "#" + v;
      if (/^#[0-9a-fA-F]{6}$/.test(v)) {
        pick.value = v;
        hex.value = v;
        applyVars();
      }
    });
  });

  editor.querySelectorAll("[data-theme-preset]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var p = presets[btn.getAttribute("data-theme-preset")];
      if (!p) return;
      Object.keys(p).forEach(function (k) { setColor(k, p[k]); });
      applyVars();
    });
  });

  applyVars();
})();
