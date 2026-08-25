(function () {
  "use strict";

  /* ============ GPA / CGPA ============ */
  const gradeScales = {
    "10": [
      { label: "A+ (10)", value: 10 }, { label: "A (9)", value: 9 },
      { label: "B+ (8)", value: 8 }, { label: "B (7)", value: 7 },
      { label: "C+ (6)", value: 6 }, { label: "C (5)", value: 5 },
      { label: "D (4)", value: 4 }, { label: "F (0)", value: 0 },
    ],
    "4": [
      { label: "A (4.0)", value: 4.0 }, { label: "A- (3.7)", value: 3.7 },
      { label: "B+ (3.3)", value: 3.3 }, { label: "B (3.0)", value: 3.0 },
      { label: "B- (2.7)", value: 2.7 }, { label: "C+ (2.3)", value: 2.3 },
      { label: "C (2.0)", value: 2.0 }, { label: "D (1.0)", value: 1.0 },
      { label: "F (0.0)", value: 0.0 },
    ],
  };

  const subjectRows = document.getElementById("subject-rows");
  const gradeScaleSelect = document.getElementById("grade-scale");

  function gradeOptionsHTML() {
    const scale = gradeScales[gradeScaleSelect.value];
    return scale.map(function (g) { return '<option value="' + g.value + '">' + g.label + "</option>"; }).join("");
  }

  function addSubjectRow(name, credits) {
    if (!subjectRows) return;
    const row = document.createElement("div");
    row.className = "subject-row";
    row.innerHTML =
      '<input type="text" class="subj-name" placeholder="Subject name" value="' + (name || "") + '">' +
      '<input type="number" class="subj-credits" placeholder="Credits" min="0" step="any" value="' + (credits || 3) + '">' +
      '<select class="subj-grade">' + gradeOptionsHTML() + "</select>" +
      '<button type="button" class="remove-subject" aria-label="Remove subject">×</button>';
    row.querySelector(".remove-subject").addEventListener("click", function () { row.remove(); });
    subjectRows.appendChild(row);
  }

  const addSubjectBtn = document.getElementById("add-subject");
  if (addSubjectBtn) {
    addSubjectBtn.addEventListener("click", function () { addSubjectRow(); });
    // seed with 3 rows
    addSubjectRow(); addSubjectRow(); addSubjectRow();
  }

  if (gradeScaleSelect) {
    gradeScaleSelect.addEventListener("change", function () {
      document.querySelectorAll(".subj-grade").forEach(function (sel) {
        sel.innerHTML = gradeOptionsHTML();
      });
    });
  }

  const gpaResult = document.getElementById("gpa-result");
  const calcGpaBtn = document.getElementById("calc-gpa");
  if (calcGpaBtn) {
    calcGpaBtn.addEventListener("click", function () {
      const rows = document.querySelectorAll(".subject-row");
      let totalPoints = 0, totalCredits = 0;
      rows.forEach(function (row) {
        const credits = parseFloat(row.querySelector(".subj-credits").value) || 0;
        const grade = parseFloat(row.querySelector(".subj-grade").value) || 0;
        totalPoints += credits * grade;
        totalCredits += credits;
      });
      const gpa = totalCredits > 0 ? (totalPoints / totalCredits) : 0;
      gpaResult.hidden = false;
      gpaResult.textContent =
        "Total credits: " + totalCredits.toFixed(1) +
        "\nGPA / CGPA: " + gpa.toFixed(2) +
        (gradeScaleSelect.value === "10" ? " / 10" : " / 4.0");
    });
  }

  /* ============ Percentage ============ */
  const calcPercentageBtn = document.getElementById("calc-percentage");
  if (calcPercentageBtn) {
    calcPercentageBtn.addEventListener("click", function () {
      const obtained = parseFloat(document.getElementById("marks-obtained").value);
      const total = parseFloat(document.getElementById("marks-total").value);
      const out = document.getElementById("percentage-result");
      out.hidden = false;
      if (!isFinite(obtained) || !isFinite(total) || total <= 0) {
        out.textContent = "Enter valid marks obtained and total marks.";
        return;
      }
      const pct = (obtained / total) * 100;
      out.textContent = "Percentage: " + pct.toFixed(2) + "%";
    });
  }

  const calcChangeBtn = document.getElementById("calc-change");
  if (calcChangeBtn) {
    calcChangeBtn.addEventListener("click", function () {
      const oldV = parseFloat(document.getElementById("value-old").value);
      const newV = parseFloat(document.getElementById("value-new").value);
      const out = document.getElementById("change-result");
      out.hidden = false;
      if (!isFinite(oldV) || !isFinite(newV) || oldV === 0) {
        out.textContent = "Enter a valid old value (non-zero) and new value.";
        return;
      }
      const change = ((newV - oldV) / Math.abs(oldV)) * 100;
      out.textContent = (change >= 0 ? "Increase" : "Decrease") + ": " + Math.abs(change).toFixed(2) + "%";
    });
  }

  /* ============ Attendance ============ */
  const calcAttendanceBtn = document.getElementById("calc-attendance");
  if (calcAttendanceBtn) {
    calcAttendanceBtn.addEventListener("click", function () {
      const total = parseFloat(document.getElementById("classes-total").value);
      const attended = parseFloat(document.getElementById("classes-attended").value);
      const target = parseFloat(document.getElementById("attendance-target").value) || 75;
      const out = document.getElementById("attendance-result");
      out.hidden = false;
      if (!isFinite(total) || !isFinite(attended) || total <= 0 || attended > total || attended < 0) {
        out.textContent = "Enter valid total and attended class counts.";
        return;
      }
      const missed = total - attended;
      const currentPct = (attended / total) * 100;
      let lines = [
        "Current attendance: " + currentPct.toFixed(2) + "%",
        "Classes missed so far: " + missed,
      ];

      if (currentPct < target) {
        // classes to attend consecutively (x) so that (attended+x)/(total+x) >= target/100
        const t = target / 100;
        const x = Math.ceil((t * total - attended) / (1 - t));
        lines.push("Classes needed (attending every one) to reach " + target + "%: " + Math.max(x, 0));
      } else {
        // classes that can still be missed (y) so that attended/(total+y) >= target/100
        const t = target / 100;
        const y = Math.floor(attended / t - total);
        lines.push("Classes you can still miss and stay at/above " + target + "%: " + Math.max(y, 0));
      }
      out.textContent = lines.join("\n");
    });
  }

  /* ============ Age ============ */
  const calcAgeBtn = document.getElementById("calc-age");
  if (calcAgeBtn) {
    calcAgeBtn.addEventListener("click", function () {
      const dobVal = document.getElementById("dob").value;
      const out = document.getElementById("age-result");
      out.hidden = false;
      if (!dobVal) { out.textContent = "Please choose a date of birth."; return; }
      const dob = new Date(dobVal + "T00:00:00");
      const now = new Date();
      if (dob > now) { out.textContent = "Date of birth can't be in the future."; return; }

      let years = now.getFullYear() - dob.getFullYear();
      let months = now.getMonth() - dob.getMonth();
      let days = now.getDate() - dob.getDate();
      if (days < 0) {
        months -= 1;
        const prevMonth = new Date(now.getFullYear(), now.getMonth(), 0);
        days += prevMonth.getDate();
      }
      if (months < 0) { months += 12; years -= 1; }

      let nextBday = new Date(now.getFullYear(), dob.getMonth(), dob.getDate());
      if (nextBday < now) nextBday.setFullYear(now.getFullYear() + 1);
      const daysToBday = Math.ceil((nextBday - now) / (1000 * 60 * 60 * 24));

      out.textContent =
        "Age: " + years + " years, " + months + " months, " + days + " days" +
        "\nNext birthday: " + nextBday.toDateString() + " (" + daysToBday + " days away)";
    });
  }

  /* ============ Unit Converter ============ */
  const unitCategories = {
    Length: { base: "m", units: { m: 1, km: 1000, cm: 0.01, mm: 0.001, mile: 1609.344, yard: 0.9144, foot: 0.3048, inch: 0.0254 } },
    Weight: { base: "kg", units: { kg: 1, g: 0.001, mg: 0.000001, lb: 0.453592, oz: 0.0283495, ton: 1000 } },
    Temperature: { special: true },
    Area: { base: "sqm", units: { sqm: 1, sqkm: 1e6, sqft: 0.092903, sqyd: 0.836127, acre: 4046.86, hectare: 10000 } },
    Volume: { base: "l", units: { l: 1, ml: 0.001, gallon: 3.78541, quart: 0.946353, cup: 0.24, m3: 1000 } },
    Speed: { base: "mps", units: { mps: 1, kmph: 0.277778, mph: 0.44704, knot: 0.514444 } },
    Time: { base: "s", units: { s: 1, min: 60, hr: 3600, day: 86400, week: 604800 } },
    Data: { base: "byte", units: { byte: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, TB: 1024 ** 4 } },
    Energy: { base: "joule", units: { joule: 1, kJ: 1000, calorie: 4.184, kcal: 4184, kWh: 3600000 } },
    Pressure: { base: "pa", units: { pa: 1, kpa: 1000, atm: 101325, bar: 100000, psi: 6894.76 } },
  };

  const catSelect = document.getElementById("conv-category");
  const fromSelect = document.getElementById("conv-from");
  const toSelect = document.getElementById("conv-to");
  const valueInput = document.getElementById("conv-value");
  const converterResult = document.getElementById("converter-result");

  function populateUnitSelects() {
    if (!catSelect) return;
    const cat = unitCategories[catSelect.value];
    const unitNames = cat.special ? ["Celsius", "Fahrenheit", "Kelvin"] : Object.keys(cat.units);
    fromSelect.innerHTML = unitNames.map(function (u) { return "<option>" + u + "</option>"; }).join("");
    toSelect.innerHTML = unitNames.map(function (u) { return "<option>" + u + "</option>"; }).join("");
    if (unitNames.length > 1) toSelect.selectedIndex = 1;
  }

  function convertTemperature(value, from, to) {
    let celsius;
    if (from === "Celsius") celsius = value;
    else if (from === "Fahrenheit") celsius = (value - 32) * 5 / 9;
    else celsius = value - 273.15;

    if (to === "Celsius") return celsius;
    if (to === "Fahrenheit") return celsius * 9 / 5 + 32;
    return celsius + 273.15;
  }

  function runConversion() {
    if (!catSelect || !converterResult) return;
    const value = parseFloat(valueInput.value);
    if (!isFinite(value)) { converterResult.textContent = "Enter a valid number."; return; }
    const cat = unitCategories[catSelect.value];
    const from = fromSelect.value, to = toSelect.value;
    let result;
    if (cat.special) {
      result = convertTemperature(value, from, to);
    } else {
      const baseValue = value * cat.units[from];
      result = baseValue / cat.units[to];
    }
    converterResult.textContent = value + " " + from + " = " + result.toFixed(6).replace(/\.?0+$/, "") + " " + to;
  }

  if (catSelect) {
    catSelect.innerHTML = Object.keys(unitCategories).map(function (c) { return "<option>" + c + "</option>"; }).join("");
    populateUnitSelects();
    runConversion();
    catSelect.addEventListener("change", function () { populateUnitSelects(); runConversion(); });
    fromSelect.addEventListener("change", runConversion);
    toSelect.addEventListener("change", runConversion);
    valueInput.addEventListener("input", runConversion);
  }

  /* ============ Scientific Calculator ============ */
  const sciDisplay = document.getElementById("sci-display");
  const sciGrid = document.getElementById("sci-grid");
  let sciExpr = "";

  const sciButtons = [
    "C", "(", ")", "←", "÷",
    "sin", "cos", "tan", "log", "×",
    "7", "8", "9", "^", "−",
    "4", "5", "6", "√", "+",
    "1", "2", "3", "π", "=",
    "0", ".", "e", "%", "ln",
  ];

  function sanitizeExpr(expr) {
    return expr
      .replace(/×/g, "*")
      .replace(/÷/g, "/")
      .replace(/−/g, "-")
      .replace(/π/g, "Math.PI")
      .replace(/\be\b/g, "Math.E")
      .replace(/√\(/g, "Math.sqrt(")
      .replace(/sin\(/g, "Math.sin(")
      .replace(/cos\(/g, "Math.cos(")
      .replace(/tan\(/g, "Math.tan(")
      .replace(/log\(/g, "Math.log10(")
      .replace(/ln\(/g, "Math.log(")
      .replace(/\^/g, "**")
      .replace(/(\d+(\.\d+)?)%/g, "($1/100)");
  }

  function handleSciButton(label) {
    if (label === "C") { sciExpr = ""; }
    else if (label === "←") { sciExpr = sciExpr.slice(0, -1); }
    else if (label === "=") {
      try {
        const expr = sanitizeExpr(sciExpr);
        // eslint-disable-next-line no-new-func
        const val = Function('"use strict"; return (' + expr + ")")();
        sciExpr = String(Math.round(val * 1e10) / 1e10);
      } catch (e) {
        sciExpr = "Error";
      }
    } else if (["sin", "cos", "tan", "log", "ln", "√"].includes(label)) {
      sciExpr += label + "(";
    } else {
      sciExpr += label;
    }
    sciDisplay.value = sciExpr || "0";
  }

  if (sciGrid) {
    sciButtons.forEach(function (label) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = label;
      if (["÷", "×", "−", "+", "="].includes(label)) btn.classList.add("op");
      btn.addEventListener("click", function () { handleSciButton(label); });
      sciGrid.appendChild(btn);
    });
  }
})();
