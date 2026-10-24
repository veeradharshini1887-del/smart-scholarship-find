/* Smart Scholarship Finder - front-end behaviour
   1. Bootstrap form validation (server still re-validates everything)
   2. Document upload checks (type and size) before sending
   3. Admin dashboard: talks to the Flask JSON API with fetch()
*/
(function () {
  "use strict";

  // 1. Bootstrap validation ------------------------------------------------
  document.querySelectorAll("form.needs-validation").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      var confirm = form.querySelector("#confirm");
      var password = form.querySelector("#password");
      if (confirm && password) {
        confirm.setCustomValidity(confirm.value === password.value ? "" : "Passwords do not match");
      }
      if (!form.checkValidity()) {
        event.preventDefault();
        event.stopPropagation();
      }
      form.classList.add("was-validated");
    });
  });

  // 2. Document upload checks ----------------------------------------------
  var MAX_BYTES = 2 * 1024 * 1024;
  var OK_EXT = ["pdf", "jpg", "jpeg", "png"];
  var uploadForm = document.getElementById("uploadForm");
  if (uploadForm) {
    var validateInput = function (input) {
      var box = input.closest(".doc-upload").querySelector(".file-error");
      var file = input.files[0];
      var message = "";
      if (file) {
        var ext = file.name.split(".").pop().toLowerCase();
        if (OK_EXT.indexOf(ext) === -1) message = "Only PDF, JPG or PNG files are allowed.";
        else if (file.size > MAX_BYTES) message = "File is larger than 2 MB.";
      }
      box.textContent = message;
      box.hidden = !message;
      return !message;
    };
    uploadForm.querySelectorAll(".doc-input").forEach(function (input) {
      input.addEventListener("change", function () { validateInput(input); });
    });
    uploadForm.addEventListener("submit", function (event) {
      var ok = true;
      uploadForm.querySelectorAll(".doc-input").forEach(function (input) { if (!validateInput(input)) ok = false; });
      if (!ok) event.preventDefault();
    });
  }

  // 3. Admin dashboard -------------------------------------------------------
  var app = document.getElementById("adminApp");
  if (!app) return;

  var csrf = document.querySelector('meta[name="csrf-token"]').content;
  var state = { scholarships: [], statuses: [] };
  var modal = new bootstrap.Modal(document.getElementById("schModal"));

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function dmy(iso) {
    if (!iso) return "";
    var p = String(iso).slice(0, 10).split("-");
    return p.length === 3 ? p[2] + "-" + p[1] + "-" + p[0] : iso;
  }
  function inr(n) { return "\u20b9" + Number(n || 0).toLocaleString("en-IN"); }

  async function api(url, method, body) {
    var options = {
      method: method || "GET",
      credentials: "same-origin",
      headers: { "Accept": "application/json", "X-Requested-With": "fetch", "X-CSRF-Token": csrf }
    };
    if (body !== undefined) {
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    var res = await fetch(url, options);
    var data = {};
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (!res.ok) {
      var err = new Error(data.error || "Request failed (" + res.status + ")");
      err.status = res.status; err.data = data;
      throw err;
    }
    return data;
  }

  var msgBox = document.getElementById("adminMsg");
  function notify(text, kind) {
    msgBox.className = "alert alert-" + (kind || "success");
    msgBox.textContent = text;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function setRows(id, html, cols, emptyText) {
    document.getElementById(id).innerHTML = html ||
      '<tr><td colspan="' + cols + '" class="text-muted p-3">' + emptyText + "</td></tr>";
  }

  // ---- Scholarships table
  async function loadScholarships() {
    var data = await api("/admin/scholarships");
    state.scholarships = data.scholarships;
    var html = data.scholarships.map(function (s) {
      return "<tr><td><strong>" + esc(s.scholarship_name) + "</strong>" +
        (s.is_demo ? ' <span class="badge-demo">Demo</span>' : "") + "</td>" +
        "<td>" + inr(s.amount) + "</td><td>" + (s.minimum_cgpa || "-") + "</td>" +
        "<td>" + (s.maximum_income ? inr(s.maximum_income) : "-") + "</td>" +
        '<td class="tiny">' + esc(s.degree) + " / " + esc(s.community) + " / " + esc(s.gender) + " / " + esc(s.state) + "</td>" +
        "<td>" + dmy(s.last_date) + "</td><td>" + s.application_count + "</td>" +
        '<td class="text-nowrap"><button class="btn btn-outline-primary btn-sm" data-edit="' + s.scholarship_id + '">Edit</button> ' +
        '<button class="btn btn-outline-danger btn-sm" data-delete="' + s.scholarship_id + '">Delete</button></td></tr>';
    }).join("");
    setRows("schBody", html, 8, "No scholarships yet. Click Add scholarship.");
    document.getElementById("statScholarships").textContent = data.scholarships.length;
  }

  // ---- Applications table (status can be changed here)
  async function loadApplications() {
    var data = await api("/admin/applications");
    state.statuses = data.statuses;
    var html = data.applications.map(function (a) {
      var options = data.statuses.map(function (s) {
        return "<option" + (s === a.application_status ? " selected" : "") + ">" + esc(s) + "</option>";
      }).join("");
      return "<tr><td>" + a.application_id + "</td><td>" + esc(a.student_name) + "</td><td>" + esc(a.college) +
        "</td><td>" + esc(a.scholarship_name) + "</td><td>" + dmy(a.applied_date) + "</td>" +
        '<td><select class="form-select form-select-sm" data-status="' + a.application_id + '" aria-label="Status">' + options + "</select></td></tr>";
    }).join("");
    setRows("appBody", html, 6, "No applications yet.");
    document.getElementById("statApplications").textContent = data.applications.length;
  }

  async function loadStudents() {
    var data = await api("/admin/students");
    var html = data.students.map(function (s) {
      return "<tr><td>" + s.student_id + "</td><td>" + esc(s.name) + "</td><td>" + esc(s.email) + "</td><td>" + esc(s.college || "-") +
        "</td><td>" + esc(s.degree || "-") + "</td><td>" + (s.cgpa == null ? "-" : s.cgpa) + "</td><td>" +
        (s.family_income == null ? "-" : inr(s.family_income)) + "</td><td>" + esc(s.community || "-") + "</td><td>" +
        esc(s.gender || "-") + "</td><td>" + esc(s.state || "-") + "</td></tr>";
    }).join("");
    setRows("stuBody", html, 10, "No students registered yet.");
    document.getElementById("statStudents").textContent = data.students.length;
  }

  async function loadDocuments() {
    var data = await api("/admin/documents");
    var fields = ["aadhaar", "income_certificate", "marksheet", "community_certificate"];
    var html = data.documents.map(function (d) {
      var cells = fields.map(function (f) {
        return d[f] ? '<td><a href="/admin/documents/' + d.student_id + "/" + f + '" target="_blank" rel="noopener">View</a></td>'
                    : '<td class="text-muted">Missing</td>';
      }).join("");
      return "<tr><td>" + esc(d.name) + "</td><td>" + esc(d.email) + "</td>" + cells + "<td>" + dmy(d.updated_at) + "</td></tr>";
    }).join("");
    setRows("docBody", html, 7, "No documents uploaded yet.");
  }

  function refreshAll() {
    return Promise.all([loadScholarships(), loadApplications(), loadStudents(), loadDocuments()])
      .catch(function (e) { notify(e.message, "danger"); });
  }

  // ---- Scholarship form (modal)
  var ids = ["sf_id", "sf_name", "sf_amount", "sf_cgpa", "sf_income", "sf_elig", "sf_degree", "sf_community", "sf_gender", "sf_state", "sf_date", "sf_link", "sf_demo"];
  function el(id) { return document.getElementById(id); }
  function openForm(s) {
    document.getElementById("schModalTitle").textContent = s ? "Edit scholarship" : "Add scholarship";
    el("sfErrors").classList.add("d-none");
    el("sf_id").value = s ? s.scholarship_id : "";
    el("sf_name").value = s ? s.scholarship_name : "";
    el("sf_amount").value = s ? s.amount : "";
    el("sf_cgpa").value = s ? s.minimum_cgpa : 0;
    el("sf_income").value = s ? s.maximum_income : 0;
    el("sf_elig").value = s ? s.eligibility : "";
    el("sf_degree").value = s ? s.degree : "ALL";
    el("sf_community").value = s ? s.community : "ALL";
    el("sf_gender").value = s ? s.gender : "All";
    el("sf_state").value = s ? s.state : "ALL";
    el("sf_date").value = s ? String(s.last_date).slice(0, 10) : "";
    el("sf_link").value = s && s.official_link ? s.official_link : "";
    el("sf_demo").checked = s ? !!s.is_demo : false;
    var chosen = s ? s.required_documents.split(",").map(function (x) { return x.trim(); }) : ["Aadhaar", "Marksheet"];
    document.querySelectorAll(".sf-doc").forEach(function (cb) { cb.checked = chosen.indexOf(cb.value) !== -1; });
    modal.show();
  }

  async function saveForm() {
    var id = el("sf_id").value;
    var payload = {
      scholarship_name: el("sf_name").value, amount: el("sf_amount").value,
      minimum_cgpa: el("sf_cgpa").value, maximum_income: el("sf_income").value,
      eligibility: el("sf_elig").value, degree: el("sf_degree").value,
      community: el("sf_community").value, gender: el("sf_gender").value, state: el("sf_state").value,
      required_documents: Array.prototype.map.call(document.querySelectorAll(".sf-doc:checked"), function (c) { return c.value; }),
      last_date: el("sf_date").value, official_link: el("sf_link").value, is_demo: el("sf_demo").checked
    };
    try {
      var result = id ? await api("/admin/scholarships/" + id, "PUT", payload) : await api("/admin/scholarships", "POST", payload);
      modal.hide();
      notify(result.message, "success");
      await loadScholarships();
    } catch (e) {
      var box = el("sfErrors");
      var fields = (e.data && e.data.fields) || {};
      var lines = Object.keys(fields).map(function (k) { return "<li>" + esc(fields[k]) + "</li>"; }).join("");
      box.innerHTML = esc(e.message) + (lines ? "<ul class='mb-0'>" + lines + "</ul>" : "");
      box.classList.remove("d-none");
    }
  }

  // ---- Events
  document.getElementById("btnAddSch").addEventListener("click", function () { openForm(null); });
  document.getElementById("btnSaveSch").addEventListener("click", saveForm);

  document.getElementById("btnDeleteDemo").addEventListener("click", async function () {
    if (!window.confirm("Remove ALL demo scholarships (and any applications made to them)?")) return;
    try { var r = await api("/admin/scholarships/demo", "DELETE"); notify(r.message); await refreshAll(); }
    catch (e) { notify(e.message, "danger"); }
  });

  document.getElementById("schBody").addEventListener("click", async function (event) {
    var editId = event.target.getAttribute("data-edit");
    var delId = event.target.getAttribute("data-delete");
    if (editId) {
      var s = state.scholarships.find(function (x) { return String(x.scholarship_id) === editId; });
      if (s) openForm(s);
    } else if (delId) {
      if (!window.confirm("Delete this scholarship?")) return;
      try {
        var r = await api("/admin/scholarships/" + delId, "DELETE");
        notify(r.message); await refreshAll();
      } catch (e) {
        if (e.status === 409 && window.confirm(e.message + " Delete anyway? Those applications will be removed too.")) {
          try { var r2 = await api("/admin/scholarships/" + delId + "?force=1", "DELETE"); notify(r2.message); await refreshAll(); }
          catch (e2) { notify(e2.message, "danger"); }
        } else if (e.status !== 409) { notify(e.message, "danger"); }
      }
    }
  });

  document.getElementById("appBody").addEventListener("change", async function (event) {
    var id = event.target.getAttribute("data-status");
    if (!id) return;
    try { var r = await api("/admin/applications/" + id, "PUT", { status: event.target.value }); notify(r.message); }
    catch (e) { notify(e.message, "danger"); await loadApplications(); }
  });

  refreshAll();
})();
