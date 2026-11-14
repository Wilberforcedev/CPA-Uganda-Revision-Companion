const toast = document.getElementById("toast");
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
let toastTimer;

function notify(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
}

async function postJSON(url, data) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-CSRF-Token": csrfToken},
    body: JSON.stringify(data)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "That action could not be completed.");
  return result;
}

function rolePages(role) {
  if (role === "student") return ["overview", "courses", "resources", "assignments", "progress"];
  if (role === "tutor") return ["overview", "courses", "resources", "planner", "assignments"];
  return ["overview", "courses", "resources", "planner", "assignments", "progress"];
}

function applyRole(role) {
  document.body.dataset.role = role;
  document.querySelectorAll("[data-roles]").forEach(element => {
    const roles = element.dataset.roles.split(/\s+/);
    element.hidden = !roles.includes(role);
  });
  if (!rolePages(role).includes(currentPage())) showPage("overview");
}

function currentPage() {
  const current = document.querySelector(".page-view.active");
  return current ? current.id.replace("view-", "") : "overview";
}

function showPage(page) {
  const titles = {
    overview: "Overview", courses: "Course directory", resources: "Learning resources",
    planner: "Class planner", assignments: "Assignments", progress: "My progress"
  };
  if (!rolePages(document.body.dataset.role || "student").includes(page)) {
    notify("That workspace is not available in this preview role.");
    return;
  }
  document.querySelectorAll(".page-view").forEach(node => node.classList.toggle("active", node.id === "view-" + page));
  document.querySelectorAll(".nav-item").forEach(node => node.classList.toggle("active", node.dataset.page === page));
  document.getElementById("page-title").textContent = titles[page] || "Overview";
  window.scrollTo({top: 0, behavior: "smooth"});
  document.querySelector(".sidebar").classList.remove("open");
}

async function openCourse(code) {
  try {
    const response = await fetch("/api/courses/" + encodeURIComponent(code));
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Course details are unavailable.");
    document.getElementById("course-code").textContent = data.course.paper + " · " + data.course.code;
    document.getElementById("course-title").textContent = data.course.title;
    document.getElementById("course-description").textContent = data.course.description;
    document.getElementById("course-progress-bar").style.width = data.course.progress + "%";
    document.getElementById("course-progress-label").textContent = data.course.progress + "%";
    const list = document.getElementById("course-resources");
    list.replaceChildren();
    if (!data.resources.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Learning materials for this paper will be added here.";
      list.append(empty);
    }
    data.resources.forEach(resource => {
      const item = document.createElement("article");
      item.className = "lesson-row";
      const copy = document.createElement("div");
      const kind = document.createElement("span");
      kind.className = "meta";
      kind.textContent = resource.kind + " · " + resource.duration;
      const title = document.createElement("h3");
      title.textContent = resource.title;
      const summary = document.createElement("p");
      summary.textContent = resource.summary;
      copy.append(kind, title, summary);
      const action = document.createElement("button");
      action.className = "resource-open";
      action.dataset.resource = resource.id;
      action.textContent = resource.completed ? "Completed ✓" : "Mark complete →";
      action.disabled = resource.completed;
      item.append(copy, action);
      list.append(item);
    });
    document.getElementById("course-dialog").showModal();
  } catch (error) {
    notify(error.message);
  }
}

function filterCourses() {
  const query = document.getElementById("course-search").value.trim().toLowerCase();
  const paper = document.getElementById("course-filter").value;
  document.querySelectorAll("#course-directory .directory-card").forEach(card => {
    card.hidden = !(card.dataset.search.includes(query) && (!paper || card.dataset.code === paper));
  });
}

function filterResources() {
  const query = document.getElementById("resource-search").value.trim().toLowerCase();
  const paper = document.getElementById("resource-filter").value;
  let shown = 0;
  document.querySelectorAll("#resource-directory .resource-card").forEach(card => {
    const visible = card.dataset.search.includes(query) && (!paper || card.dataset.code === paper);
    card.hidden = !visible;
    if (visible) shown++;
  });
  document.getElementById("resource-empty").hidden = shown > 0;
}

document.addEventListener("click", async event => {
  const page = event.target.closest("[data-page]");
  if (page) { showPage(page.dataset.page); return; }

  const toastButton = event.target.closest("[data-toast]");
  if (toastButton) { notify(toastButton.dataset.toast); return; }

  const course = event.target.closest("[data-course]");
  if (course) { openCourse(course.dataset.course); return; }

  const enroll = event.target.closest("[data-enroll]");
  if (enroll) {
    try {
      const result = await postJSON("/api/enroll", {course_code: enroll.dataset.enroll});
      enroll.textContent = "In your plan ✓";
      enroll.disabled = true;
      notify(result.message);
    } catch (error) { notify(error.message); }
    return;
  }

  const resource = event.target.closest("[data-resource]");
  if (resource) {
    try {
      const result = await postJSON("/api/complete", {resource_id: Number(resource.dataset.resource)});
      notify(result.message);
      resource.textContent = "Completed ✓";
      resource.disabled = true;
      setTimeout(() => location.reload(), 650);
    } catch (error) { notify(error.message); }
    return;
  }

  const assignment = event.target.closest("[data-assignment]");
  if (assignment) {
    const dialog = document.getElementById("task-dialog");
    const row = assignment.closest("tr");
    document.getElementById("dialog-title").textContent = row.querySelector("td strong").textContent;
    document.getElementById("submit-response").dataset.assignmentId = assignment.dataset.assignment;
    document.getElementById("dialog-answer").value = "";
    dialog.showModal();
  }
});

document.querySelector(".mobile-menu").addEventListener("click", () => {
  document.querySelector(".sidebar").classList.toggle("open");
});

document.getElementById("role-switch").addEventListener("change", async event => {
  try {
    const result = await postJSON("/api/role", {role: event.target.value});
    applyRole(result.role);
    notify("Preview switched to " + result.role + ".");
  } catch (error) { notify(error.message); }
});

document.getElementById("course-search").addEventListener("input", filterCourses);
document.getElementById("course-filter").addEventListener("change", filterCourses);
document.getElementById("resource-search").addEventListener("input", filterResources);
document.getElementById("resource-filter").addEventListener("change", filterResources);
document.getElementById("reset-search").addEventListener("click", () => {
  document.getElementById("resource-search").value = "";
  document.getElementById("resource-filter").value = "";
  filterResources();
});

document.getElementById("class-form").addEventListener("submit", async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  try {
    const result = await postJSON("/api/class-sites", data);
    notify(result.message);
    event.currentTarget.reset();
    setTimeout(() => location.reload(), 650);
  } catch (error) { notify(error.message); }
});

document.getElementById("assignment-form").addEventListener("submit", async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.currentTarget));
  try {
    const result = await postJSON("/api/assignments", data);
    notify(result.message);
    event.currentTarget.reset();
    setTimeout(() => location.reload(), 650);
  } catch (error) { notify(error.message); }
});

document.getElementById("submit-response").addEventListener("click", async () => {
  const answer = document.getElementById("dialog-answer").value;
  const assignment_id = Number(document.getElementById("submit-response").dataset.assignmentId);
  try {
    const result = await postJSON("/api/submit", {assignment_id, answer});
    document.getElementById("task-dialog").close();
    notify(result.message);
    setTimeout(() => location.reload(), 650);
  } catch (error) { notify(error.message); }
});

const dateLabel = document.getElementById("date-label");
if (dateLabel) {
  const now = new Date();
  const hour = now.getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const name = document.querySelector(".profile strong").textContent;
  const heading = document.querySelector(".welcome-row h1");
  heading.firstChild.textContent = greeting + ", " + name + " ";
  dateLabel.textContent = now.toLocaleDateString("en-UG", {weekday:"long", month:"long", day:"numeric"}).toUpperCase() + " · YOUR LEARNING SPACE";
}

applyRole(document.body.dataset.role || "student");
