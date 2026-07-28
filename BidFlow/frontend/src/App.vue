<script setup>
import { computed, onMounted, ref } from 'vue'
import { getCurrentUser, login, register } from './api/auth'
import { createProject, getProject, listProjects, listRequirements, parseTender, updateRequirement, uploadTender } from './api/projects'
import { generateDraft, getDraft, reportUrl, runCompliance, updateDraft } from './api/compliance'
import { deleteMaterial, listMaterials, searchMaterials, uploadMaterial } from './api/materials'

const token = ref(localStorage.getItem('bidflow_token') || '')
const user = ref(null)
const mode = ref('login')
const authForm = ref({ username: '', password: '' })
const authError = ref('')
const busy = ref(false)
const notice = ref('')
const projects = ref([])
const selectedProject = ref(null)
const requirements = ref([])
const selectedRequirement = ref(null)
const draft = ref(null)
const report = ref(null)
const file = ref(null)
const newProject = ref({ name: '', tenderer: '', description: '', deadline: '' })
const sourceText = ref('')
const materialFile = ref(null)
const materials = ref([])

const loggedIn = computed(() => Boolean(token.value && user.value))
const projectId = computed(() => selectedProject.value?.id)

function say(message) { notice.value = message; setTimeout(() => { if (notice.value === message) notice.value = '' }, 3500) }
function unwrap(response) { return response?.data ?? response }
function onFile(event) { file.value = event.target.files?.[0] || null }

async function submitAuth() {
  authError.value = ''; busy.value = true
  try {
    if (mode.value === 'register') await register(authForm.value)
    const session = await login(authForm.value)
    token.value = session.access_token
    localStorage.setItem('bidflow_token', token.value)
    user.value = await getCurrentUser()
    await refreshProjects(); await refreshMaterials()
    say(mode.value === 'register' ? '注册并登录成功' : '登录成功')
  } catch (error) { authError.value = error.message } finally { busy.value = false }
}

async function refreshProjects() {
  const response = await listProjects()
  projects.value = unwrap(response) || []
}

async function refreshMaterials() {
  try { materials.value = await listMaterials() } catch { materials.value = [] }
}

function onMaterialFile(event) { materialFile.value = event.target.files?.[0] || null }

async function submitMaterial() {
  if (!materialFile.value) return say('请选择企业资料文件')
  busy.value = true
  try {
    const result = await uploadMaterial(materialFile.value)
    await refreshMaterials()
    say(`资料已入库，共 ${result.chunk_count} 个可检索片段`)
  } catch (error) { say(error.message) } finally { busy.value = false }
}

async function removeMaterial(id) {
  busy.value = true
  try { await deleteMaterial(id); await refreshMaterials(); say('资料已删除') } catch (error) { say(error.message) } finally { busy.value = false }
}

async function openProject(project) {
  busy.value = true
  try {
    selectedProject.value = unwrap(await getProject(project.id))
    requirements.value = unwrap(await listRequirements(project.id)) || []
    report.value = null; selectedRequirement.value = null; draft.value = null
  } catch (error) { say(error.message) } finally { busy.value = false }
}

async function submitProject() {
  if (!newProject.value.name.trim()) return say('请填写项目名称')
  busy.value = true
  try {
    const payload = { ...newProject.value }
    if (!payload.deadline) delete payload.deadline
    selectedProject.value = unwrap(await createProject(payload))
    newProject.value = { name: '', tenderer: '', description: '', deadline: '' }
    await refreshProjects(); await openProject(selectedProject.value)
    say('项目已创建')
  } catch (error) { say(error.message) } finally { busy.value = false }
}

async function submitFile() {
  if (!file.value || !projectId.value) return say('请选择 TXT、PDF 或 DOCX 招标文件')
  busy.value = true
  try {
    const uploaded = unwrap(await uploadTender(projectId.value, file.value))
    const parsed = unwrap(await parseTender(uploaded.id))
    requirements.value = unwrap(await listRequirements(projectId.value)) || []
    say(`解析完成，识别 ${parsed.requirement_count} 条需求`)
  } catch (error) { say(error.message) } finally { busy.value = false }
}

async function selectRequirement(item) {
  selectedRequirement.value = item; draft.value = null
  try { draft.value = await getDraft(item.id) } catch { draft.value = null }
}

async function saveRequirement(item) {
  try {
    const saved = unwrap(await updateRequirement(item.id, { status: item.status, priority: item.priority, content: item.content }))
    Object.assign(item, saved); say('需求已保存')
  } catch (error) { say(error.message) }
}

async function createDraft() {
  if (!selectedRequirement.value) return
  busy.value = true
  try {
    let sources = sourceText.value.trim() ? [{ content: sourceText.value.trim(), filename: '人工补充资料', source_ref: '前端录入', score: 1 }] : []
    if (!sources.length) sources = await searchMaterials(selectedRequirement.value.content)
    draft.value = await generateDraft({ requirement_id: selectedRequirement.value.id, sources })
    say(draft.value.status === 'needs_manual' ? '资料不足，已生成待人工补充草稿' : 'AI 草稿已生成')
  } catch (error) { say(error.message) } finally { busy.value = false }
}

async function saveDraft(status) {
  if (!draft.value || !selectedRequirement.value) return
  busy.value = true
  try {
    draft.value = await updateDraft(selectedRequirement.value.id, { edited_content: draft.value.edited_content ?? draft.value.ai_content, status })
    say(status === 'completed' ? '草稿已审核完成' : '草稿已保存')
  } catch (error) { say(error.message) } finally { busy.value = false }
}

async function checkCompliance() {
  if (!projectId.value) return
  busy.value = true
  try { report.value = await runCompliance(projectId.value); say('合规核查完成') } catch (error) { say(error.message) } finally { busy.value = false }
}

function logout() { localStorage.removeItem('bidflow_token'); token.value = ''; user.value = null; selectedProject.value = null }

onMounted(async () => {
  if (!token.value) return
  try { user.value = await getCurrentUser(); await refreshProjects(); await refreshMaterials() } catch { logout() }
})
</script>

<template>
  <main v-if="!loggedIn" class="login-shell">
    <section class="login-card">
      <div class="brand-mark">BF</div>
      <p class="eyebrow">BIDFLOW AI</p><h1>投标文件智能编制<br>与合规核查平台</h1>
      <p class="muted">从需求解析到响应审查，一条链路完成投标准备。</p>
      <form @submit.prevent="submitAuth" class="form-stack">
        <label>用户名<input v-model.trim="authForm.username" required minlength="3" placeholder="至少 3 个字符"></label>
        <label>密码<input v-model="authForm.password" required minlength="6" type="password" placeholder="至少 6 位"></label>
        <p v-if="authError" class="error">{{ authError }}</p>
        <button class="primary" :disabled="busy">{{ busy ? '处理中…' : mode === 'login' ? '登录并进入工作台' : '注册并进入工作台' }}</button>
      </form>
      <button class="text-button" @click="mode = mode === 'login' ? 'register' : 'login'">{{ mode === 'login' ? '没有账号？立即注册' : '已有账号？去登录' }}</button>
    </section>
  </main>

  <main v-else class="app-shell">
    <aside class="sidebar"><div class="logo"><span>BF</span> BidFlow</div><p>AI 招投标工作台</p><button class="nav active">项目工作台</button><button class="nav" @click="checkCompliance" :disabled="!projectId">合规核查</button><div class="sidebar-bottom"><strong>{{ user.username }}</strong><button class="text-button" @click="logout">退出登录</button></div></aside>
    <section class="workspace">
      <header><div><p class="eyebrow">PROJECT CONSOLE</p><h2>{{ selectedProject ? selectedProject.name : '项目工作台' }}</h2></div><button v-if="projectId" class="secondary" @click="checkCompliance">运行合规核查</button></header>
      <p v-if="notice" class="notice">{{ notice }}</p>

      <div v-if="!selectedProject" class="project-home">
        <section class="card create-card"><h3>新建投标项目</h3><div class="form-grid"><label>项目名称<input v-model="newProject.name" placeholder="例如：智慧园区建设项目"></label><label>招标单位<input v-model="newProject.tenderer" placeholder="例如：某某信息中心"></label><label>截止日期<input v-model="newProject.deadline" type="datetime-local"></label><label>项目说明<input v-model="newProject.description" placeholder="可选"></label></div><button class="primary" @click="submitProject" :disabled="busy">创建并进入项目</button></section>
        <section class="card"><div class="section-title"><h3>我的项目</h3><button class="text-button" @click="refreshProjects">刷新</button></div><div v-if="projects.length" class="project-grid"><button v-for="item in projects" :key="item.id" class="project-card" @click="openProject(item)"><span :class="['status', item.status]">{{ item.status }}</span><h3>{{ item.name }}</h3><p>{{ item.tenderer || '未填写招标单位' }}</p><footer><span>{{ item.requirement_count || 0 }} 项需求</span><span>{{ item.risk_count || 0 }} 个风险</span></footer></button></div><p v-else class="empty">还没有项目，先创建一个开始演示。</p></section>
      </div>

      <div v-else class="detail-grid">
        <section class="card upload-card"><div class="section-title"><h3>01 · 招标文件解析</h3><button class="text-button" @click="selectedProject = null">返回项目列表</button></div><p class="muted">上传 TXT、PDF、DOCX，系统自动拆分并提取需求项。</p><input type="file" accept=".txt,.pdf,.docx,.doc" @change="onFile"><button class="primary" @click="submitFile" :disabled="busy">上传并解析</button></section>
        <section class="card materials-card"><div class="section-title"><h3>企业资料库 <small>{{ materials.length }} 份</small></h3><button class="text-button" @click="refreshMaterials">刷新</button></div><p class="muted">上传资质、案例、产品资料；草稿生成会自动检索相关内容。</p><div class="material-upload"><input type="file" accept=".txt,.pdf,.docx,.doc" @change="onMaterialFile"><button class="secondary" @click="submitMaterial" :disabled="busy">入库并向量化</button></div><div v-if="materials.length" class="material-list"><div v-for="item in materials" :key="item.id"><span>{{ item.filename }}</span><small :class="['status', item.status]">{{ item.status }}</small><button class="text-button" @click="removeMaterial(item.id)">删除</button></div></div></section>
        <section class="card"><div class="section-title"><h3>02 · 需求清单 <small>{{ requirements.length }} 项</small></h3><button class="text-button" @click="openProject(selectedProject)">刷新</button></div><div v-if="requirements.length" class="requirement-list"><button v-for="item in requirements" :key="item.id" :class="['requirement-row', { selected: selectedRequirement?.id === item.id }]" @click="selectRequirement(item)"><b :class="['priority', item.priority]">{{ item.priority }}</b><span>{{ item.content }}</span><em>{{ item.status }}</em></button></div><p v-else class="empty">上传并解析招标文件后，需求项会显示在这里。</p></section>
        <section v-if="selectedRequirement" class="card response-card"><div class="section-title"><h3>03 · 响应草稿</h3><span :class="['status', draft?.status]">{{ draft?.status || '未生成' }}</span></div><p class="requirement-source">{{ selectedRequirement.content }}</p><label>补充资料依据（可选；留空时自动检索资料库）<textarea v-model="sourceText" placeholder="例如：我司已取得 ISO9001 认证，并具备类似项目交付经验。"></textarea></label><button class="secondary" @click="createDraft" :disabled="busy">{{ sourceText ? '按补充资料生成' : '自动检索并生成草稿' }}</button><template v-if="draft"><label>草稿内容<textarea v-model="draft.edited_content" :placeholder="draft.ai_content" rows="8"></textarea></label><div class="button-row"><button class="secondary" @click="saveDraft('pending_review')">保存草稿</button><button class="primary" @click="saveDraft('completed')">审核完成</button></div></template></section>
        <section v-if="report" class="card report-card"><div class="section-title"><h3>04 · 合规报告</h3><a :href="reportUrl(projectId)" target="_blank">导出 Markdown</a></div><div class="metrics"><div><strong>{{ report.completion_rate }}%</strong><span>完成度</span></div><div><strong>{{ report.risk_count }}</strong><span>风险项</span></div><div><strong>{{ report.completed_count }}/{{ report.total_requirements }}</strong><span>已完成</span></div></div><div v-for="item in [...report.high_risks, ...report.medium_risks, ...report.low_risks]" :key="item.id" class="risk"><b :class="['risk-level', item.level]">{{ item.level }}风险</b><div><strong>{{ item.description }}</strong><p>{{ item.suggestion }}</p></div></div><p v-if="report.risk_count === 0" class="empty">当前没有风险项。</p></section>
      </div>
    </section>
  </main>
  <div v-if="busy" class="loading">正在处理，请稍候…</div>
</template>
