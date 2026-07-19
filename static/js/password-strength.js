document.addEventListener("DOMContentLoaded", function () {
  var levels = ["Very Weak", "Weak", "Fair", "Good", "Strong"];
  var colors = ["#a8433a", "#b8902e", "#b8902e", "#2d6a4f", "#1b4332"];

  document.querySelectorAll(".pw-strength-input").forEach(function (input) {
    var meter = document.createElement("div");
    meter.className = "pw-strength-meter";
    meter.innerHTML =
      '<div class="pw-strength-track"><div class="pw-strength-bar"></div></div>' +
      '<small class="pw-strength-label"></small>';
    input.insertAdjacentElement("afterend", meter);

    var bar = meter.querySelector(".pw-strength-bar");
    var label = meter.querySelector(".pw-strength-label");

    input.addEventListener("input", function () {
      var val = input.value;
      if (!val) {
        bar.style.width = "0%";
        label.textContent = "";
        return;
      }
      var score = 0;
      if (val.length >= 6) score++;
      if (val.length >= 10) score++;
      if (/[A-Z]/.test(val)) score++;
      if (/[0-9]/.test(val)) score++;
      if (/[^A-Za-z0-9]/.test(val)) score++;
      var index = Math.min(score, levels.length - 1);
      bar.style.width = ((index + 1) / levels.length) * 100 + "%";
      bar.style.backgroundColor = colors[index];
      label.textContent = "Password strength: " + levels[index];
      label.style.color = colors[index];
    });
  });
});
