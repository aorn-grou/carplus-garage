// CAR PLUS — petits outils de l'interface (fonctionne sans Internet)
(function () {
  // Jeton de sécurité pour les requêtes HTMX
  document.addEventListener("htmx:configRequest", function (e) {
    var t = document.querySelector("meta[name=csrf-token]");
    if (t) e.detail.headers["X-CSRFToken"] = t.content;
  });

  // Recherche globale : Ctrl+K ou « / » pour y aller, Échap pour fermer
  document.addEventListener("keydown", function (e) {
    var champ = document.getElementById("recherche-globale");
    if (!champ) return;
    var tag = (document.activeElement || {}).tagName;
    if ((e.ctrlKey && e.key.toLowerCase() === "k") || (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA")) {
      e.preventDefault(); champ.focus(); champ.select();
    }
    if (e.key === "Escape") { document.getElementById("resultats").innerHTML = ""; champ.blur(); }
    if (e.key === "ArrowDown" && document.activeElement === champ) {
      var premier = document.querySelector("#resultats a"); if (premier) { e.preventDefault(); premier.focus(); }
    }
  });
  document.addEventListener("click", function (e) {
    var zone = document.querySelector(".search");
    if (zone && !zone.contains(e.target)) { var r = document.getElementById("resultats"); if (r) r.innerHTML = ""; }
    var ligne = e.target.closest("tr[data-href]");
    if (ligne && !e.target.closest("a,button,form,.ed")) window.location = ligne.dataset.href;
  });

  // Menu sur tablette
  window.basculerMenu = function () { document.body.classList.toggle("menu-ouvert"); };

  // ---- Compression des photos AVANT l'envoi (factures et dégâts) ----
  var MAX = 1600, QUALITE = 0.7;
  function compresser(fichier) {
    return new Promise(function (ok, ko) {
      if (!fichier.type.match(/^image\//)) return ok(fichier);
      var img = new Image(), url = URL.createObjectURL(fichier);
      img.onload = function () {
        var l = img.naturalWidth, h = img.naturalHeight, r = Math.min(1, MAX / Math.max(l, h));
        var c = document.createElement("canvas");
        c.width = Math.round(l * r); c.height = Math.round(h * r);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        c.toBlob(function (b) {
          if (!b || b.size >= fichier.size) return ok(fichier);
          ok(new File([b], fichier.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" }));
        }, "image/jpeg", QUALITE);
      };
      img.onerror = function () { URL.revokeObjectURL(url); ok(fichier); };
      img.src = url;
    });
  }
  function ko(n) { return (n / 1024).toFixed(0) + " Ko"; }
  document.addEventListener("change", function (e) {
    var input = e.target;
    if (input.type !== "file" || !input.files.length || input.dataset.compresse === "1") return;
    var original = input.files[0];
    var info = input.parentNode.querySelector(".compression-info");
    if (!info) { info = document.createElement("div"); info.className = "compression-info"; input.after(info); }
    info.textContent = "Compression de la photo…";
    compresser(original).then(function (f) {
      var dt = new DataTransfer(); dt.items.add(f);
      input.dataset.compresse = "1"; input.files = dt.files; input.dataset.compresse = "";
      info.textContent = "Photo prête : " + ko(original.size) + " → " + ko(f.size);
      var ap = input.parentNode.querySelector(".apercu");
      if (!ap) { ap = document.createElement("img"); ap.className = "apercu"; info.after(ap); }
      ap.src = URL.createObjectURL(f); ap.style.display = "block";
    });
  });

  // Empêche le double envoi (double clic)
  document.addEventListener("submit", function (e) {
    var f = e.target;
    if (f.dataset.envoye) { e.preventDefault(); return; }
    f.dataset.envoye = "1";
    setTimeout(function () { delete f.dataset.envoye; }, 4000);
  });

  // Dépense : afficher/masquer les champs selon « avec facture »
  function majFacture() {
    var cb = document.getElementById("id_avec_facture");
    if (!cb) return;
    document.querySelectorAll("[data-si-facture]").forEach(function (el) { el.style.display = cb.checked ? "" : "none"; });
    document.querySelectorAll("[data-sans-facture]").forEach(function (el) { el.style.display = cb.checked ? "none" : ""; });
  }
  document.addEventListener("change", function (e) { if (e.target.id === "id_avec_facture") majFacture(); });
  document.addEventListener("DOMContentLoaded", majFacture);
})();

// Copier le message prêt (pour Facebook/Messenger ou autre)
window.copierMessage = function (el) {
  var t = el.dataset.message || "";
  function ok() { var o = el.textContent; if (el.tagName === "BUTTON") { el.textContent = "Message copié ✓"; setTimeout(function () { el.textContent = o; }, 1800); } }
  if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(t).then(ok); return; }
  var z = document.createElement("textarea"); z.value = t; document.body.appendChild(z); z.select();
  try { document.execCommand("copy"); ok(); } catch (e) {} document.body.removeChild(z);
};

// Thème clair / automatique / sombre (mémorisé sur cet appareil)
(function () {
  function appliquer(choix) {
    var r = document.documentElement;
    if (choix === "clair" || choix === "sombre") r.dataset.theme = choix; else delete r.dataset.theme;
    document.querySelectorAll("[data-theme-choix]").forEach(function (b) {
      b.setAttribute("aria-pressed", b.dataset.themeChoix === (choix || "auto") ? "true" : "false");
    });
  }
  var choix = "auto";
  try { choix = localStorage.getItem("carplus-theme") || "auto"; } catch (e) {}
  document.addEventListener("DOMContentLoaded", function () { appliquer(choix); });
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-theme-choix]");
    if (!b) return;
    choix = b.dataset.themeChoix;
    try { localStorage.setItem("carplus-theme", choix); } catch (err) {}
    appliquer(choix);
  });
})();
