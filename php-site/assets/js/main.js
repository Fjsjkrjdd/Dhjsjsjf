(function () {
  "use strict";

  // -- Mobile menu -----------------------------------------------------
  var toggle = document.getElementById("navToggle");
  var header = document.getElementById("siteHeader");
  if (toggle && header) {
    toggle.addEventListener("click", function () {
      header.classList.toggle("open");
    });
  }

  // -- Booking: sync online-payment amount with selected service -------
  var select = document.querySelector("[data-service-select]");
  var amount = document.querySelector("[data-pay-amount]");
  if (select && amount) {
    var sync = function () {
      var opt = select.options[select.selectedIndex];
      var price = parseInt(opt.getAttribute("data-price") || "0", 10);
      amount.textContent = price.toLocaleString("ru-RU");
    };
    select.addEventListener("change", sync);
    sync();
  }

  // -- Diploma gallery: horizontal scroll + lightbox -------------------
  document.querySelectorAll("[data-gallery]").forEach(function (gallery) {
    var track = gallery.querySelector("[data-gallery-track]");
    var prev = gallery.querySelector("[data-gallery-prev]");
    var next = gallery.querySelector("[data-gallery-next]");
    if (prev) prev.addEventListener("click", function () { track.scrollBy({ left: -track.clientWidth * 0.8, behavior: "smooth" }); });
    if (next) next.addEventListener("click", function () { track.scrollBy({ left: track.clientWidth * 0.8, behavior: "smooth" }); });
  });

  var items = Array.prototype.slice.call(document.querySelectorAll("[data-gallery-item]"));
  if (items.length) {
    var current = 0;
    var box, imgEl, capEl;

    function build() {
      box = document.createElement("div");
      box.className = "lightbox";
      box.innerHTML =
        '<button class="lb-btn lb-close" aria-label="Закрыть">×</button>' +
        '<button class="lb-btn lb-prev" aria-label="Назад">‹</button>' +
        '<figure><img alt=""><figcaption></figcaption></figure>' +
        '<button class="lb-btn lb-next" aria-label="Вперёд">›</button>';
      imgEl = box.querySelector("img");
      capEl = box.querySelector("figcaption");
      box.addEventListener("click", function (e) { if (e.target === box) close(); });
      box.querySelector(".lb-close").addEventListener("click", close);
      box.querySelector(".lb-prev").addEventListener("click", function (e) { e.stopPropagation(); show(current - 1); });
      box.querySelector(".lb-next").addEventListener("click", function (e) { e.stopPropagation(); show(current + 1); });
      document.body.appendChild(box);
    }

    function show(i) {
      current = (i + items.length) % items.length;
      var el = items[current];
      imgEl.src = el.getAttribute("data-src");
      imgEl.alt = el.getAttribute("data-title") || "";
      var t = el.getAttribute("data-title") || "";
      var d = el.getAttribute("data-desc") || "";
      capEl.textContent = d ? t + " — " + d : t;
    }

    function open(i) {
      if (!box) build();
      show(i);
      box.style.display = "flex";
      document.body.style.overflow = "hidden";
    }

    function close() {
      if (box) box.style.display = "none";
      document.body.style.overflow = "";
    }

    items.forEach(function (el, i) {
      el.addEventListener("click", function () { open(i); });
    });

    document.addEventListener("keydown", function (e) {
      if (!box || box.style.display !== "flex") return;
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") show(current + 1);
      if (e.key === "ArrowLeft") show(current - 1);
    });
  }
})();
