const toast = document.getElementById("toast");
let toastTimer;
function notify(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2800);
}
async function postJSON(url, data) {
  const response = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "That action could not be completed.");
  return result;
}
function showPage(page) {
  const titles = {overview:"Overview",courses:"Course directory",resources:"Learning resources",planner:"Class planner",assignments:"Assignments",progress:"My progress"};
  document.querySelectorAll(".page-view").forEach(node => node.classList.toggle("active", node.id === "view-" + page));
  document.querySelectorAll(".nav-item").forEach(node => node.classList.toggle("active", node.dataset.page === page));
  document.getElementById("page-title").textContent = titles[page] || "Overview";
  window.scrollTo({top:0,behavior:"smooth"});
  document.querySelector(".sidebar").classList.remove("open");
}
document.addEventListener("click", async event => {
  const page = event.target.closest("[data-page]");
  if (page) { showPage(page.dataset.page); return; }
  const toastButton = event.target.closest("[data-toast]");
  if (toastButton) { notify(toastButton.dataset.toast); return; }
  const course = event.target.closest("[data-course]");
  if (course) { showPage("courses"); document.getElementById("course-filter").value = course.dataset.course; filterCourses(); return; }
  const enroll = event.target.closest("[data-enroll]");
  if (enroll) { try { notify((await postJSON("/api/enroll",{course_code:enroll.dataset.enroll})).message); } catch(e) { notify(e.message); } return; }
  const resource = event.target.closest("[data-resource]");
  if (resource) {
    try { notify((await postJSON("/api/complete",{resource_id:Number(resource.dataset.resource)})).message); resource.textContent="Completed ✓"; resource.disabled=true; }
    catch(e) { notify(e.message); } return;
  }
  const assignment = event.target.closest("[data-assignment]");
  if (assignment) {
    const dialog=document.getElementById("task-dialog");
    document.getElementById("dialog-title").textContent=assignment.closest("tr").querySelector("td strong").textContent;
    document.getElementById("submit-response").dataset.assignmentId=assignment.dataset.assignment;
    document.getElementById("dialog-answer").value="";
    dialog.showModal();
  }
});
document.querySelectorAll(".nav-item").forEach(button => button.addEventListener("click",()=>showPage(button.dataset.page)));
document.querySelector(".mobile-menu").addEventListener("click",()=>document.querySelector(".sidebar").classList.toggle("open"));
document.getElementById("role-switch").addEventListener("change",async event=>{
  try { const r=await postJSON("/api/role",{role:event.target.value}); document.body.dataset.role=r.role; notify("Preview switched to "+r.role+"."); }
  catch(e) { notify(e.message); }
});
function filterCourses() {
  const q=document.getElementById("course-search").value.trim().toLowerCase(), code=document.getElementById("course-filter").value;
  document.querySelectorAll("#course-directory .directory-card").forEach(card=>card.hidden=!(card.dataset.search.includes(q)&&(!code||card.dataset.code===code)));
}
function filterResources() {
  const q=document.getElementById("resource-search").value.trim().toLowerCase(), code=document.getElementById("resource-filter").value; let shown=0;
  document.querySelectorAll("#resource-directory .resource-card").forEach(card=>{const ok=card.dataset.search.includes(q)&&(!code||card.dataset.code===code);card.hidden=!ok;if(ok)shown++;});
  document.getElementById("resource-empty").hidden=shown>0;
}
document.getElementById("course-search").addEventListener("input",filterCourses);
document.getElementById("course-filter").addEventListener("change",filterCourses);
document.getElementById("resource-search").addEventListener("input",filterResources);
document.getElementById("resource-filter").addEventListener("change",filterResources);
document.getElementById("reset-search").addEventListener("click",()=>{document.getElementById("resource-search").value="";document.getElementById("resource-filter").value="";filterResources();});
document.getElementById("class-form").addEventListener("submit",async e=>{
  e.preventDefault();const data=Object.fromEntries(new FormData(e.currentTarget));
  try{notify((await postJSON("/api/class-sites",data)).message);e.currentTarget.reset();setTimeout(()=>location.reload(),650);}catch(err){notify(err.message);}
});
document.getElementById("assignment-form").addEventListener("submit",async e=>{
  e.preventDefault();const data=Object.fromEntries(new FormData(e.currentTarget));
  try{notify((await postJSON("/api/assignments",data)).message);e.currentTarget.reset();setTimeout(()=>location.reload(),650);}catch(err){notify(err.message);}
});
document.getElementById("submit-response").addEventListener("click",async()=>{
  const answer=document.getElementById("dialog-answer").value, assignment_id=Number(document.getElementById("submit-response").dataset.assignmentId);
  try{notify((await postJSON("/api/submit",{assignment_id,answer})).message);document.getElementById("task-dialog").close();setTimeout(()=>location.reload(),650);}catch(e){notify(e.message);}
});
const dateLabel=document.getElementById("date-label");
if(dateLabel) dateLabel.textContent=new Date().toLocaleDateString("en-UG",{weekday:"long",month:"long",day:"numeric"}).toUpperCase()+" · YOUR LEARNING SPACE";
