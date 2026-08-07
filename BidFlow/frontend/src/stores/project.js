import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getProjects as getProjectsApi,
  getProject as getProjectApi,
  createProject as createProjectApi,
  updateProject as updateProjectApi,
  deleteProject as deleteProjectApi,
  uploadTender as uploadTenderApi,
  listTenderDocuments as listTenderDocumentsApi,
  deleteTenderDocument as deleteTenderDocumentApi,
  parseTenderDocument as parseTenderDocumentApi,
  getRequirements as getRequirementsApi,
  updateRequirement as updateRequirementApi,
} from '@/api/projects'
import { ElMessage } from 'element-plus'
import { parseResponse, parseArray } from '@/utils/api'

export const useProjectStore = defineStore('project', () => {
  const projects = ref([])
  const currentProject = ref(null)
  const requirements = ref([])
  const tenderDocs = ref([])
  const loading = ref(false)
  const parseLoading = ref(false)
  const filters = ref({
    search: '',
    status: 'all'
  })

  const totalProjects = computed(() => projects.value.length)

  const filteredProjects = computed(() => {
    return projects.value.filter(p => {
      if (filters.value.search && !p.name.includes(filters.value.search)) return false
      if (filters.value.status !== 'all' && p.status !== filters.value.status) return false
      return true
    })
  })

  const stats = computed(() => {
    const all = projects.value
    const total = all.length
    const prepared = all.filter(p => p.status === '准备中').length
    const reviewing = all.filter(p => p.status === '审核中').length
    const completed = all.filter(p => p.status === '已完成').length
    const totalRisks = all.reduce((sum, p) => sum + (p.risk_count || 0), 0)
    return [
      { label: '项目总数', value: String(total), icon: 'assessment', isRisk: false },
      { label: '准备中', value: String(prepared), icon: 'pending', isRisk: false },
      { label: '审核中', value: String(reviewing), icon: 'speed', isRisk: false },
      { label: '已完成', value: String(completed), icon: 'check_circle', isRisk: false },
      { label: '待处理风险', value: String(totalRisks), icon: 'warning', isRisk: true }
    ]
  })

  function normalizeProject(item) {
    return {
      id: item.id,
      name: item.name,
      tenderer: item.tenderer || item.agency,
      deadline: item.deadline,
      budget: item.budget,
      description: item.description,
      status: item.status,
      requirement_count: item.requirement_count,
      risk_count: item.risk_count,
      completionRate: item.completion_rate ?? 0,
      readiness: item.readiness || null,
      // M9：比对分析结果随项目持久化，避免 view-local ref 在 tab 切换/重挂载后清空导致"查不到"
      matchAnalysis: item.match_analysis || null,
      created_at: item.created_at,
      updated_at: item.updated_at,
    }
  }

  function setMatchAnalysis(id, data) {
    // id 可能来自路由参数（字符串 '19'）或数字（19），统一转字符串比较，
    // 避免严格相等类型不匹配导致比对结果静默写不进去
    if (currentProject.value?.id !== undefined && String(currentProject.value.id) === String(id)) {
      currentProject.value = { ...currentProject.value, matchAnalysis: data }
    }
  }

  async function fetchProjects(params = {}) {
    loading.value = true
    try {
      const res = await getProjectsApi(params)
      const list = parseArray(res)
      projects.value = list.map(normalizeProject)
    } catch (error) {
      ElMessage.error(error.message || '获取项目列表失败')
    } finally {
      loading.value = false
    }
  }

  async function fetchProject(id) {
    loading.value = true
    try {
      const res = await getProjectApi(id)
      const data = parseResponse(res)
      currentProject.value = data ? normalizeProject(data) : null
      return currentProject.value
    } catch (error) {
      ElMessage.error(error.message || '获取项目详情失败')
      return null
    } finally {
      loading.value = false
    }
  }

  async function createProject(projectData) {
    try {
      const res = await createProjectApi(projectData)
      projects.value.unshift(normalizeProject(res.data))
      ElMessage.success('项目创建成功')
      return res.data
    } catch (error) {
      ElMessage.error(error.response?.data?.message || '创建项目失败')
      throw error
    }
  }

  async function updateProject(id, projectData) {
    try {
      const res = await updateProjectApi(id, projectData)
      const idx = projects.value.findIndex(p => p.id === id)
      if (idx !== -1) projects.value[idx] = normalizeProject(res.data)
      if (currentProject.value?.id === id) currentProject.value = normalizeProject(res.data)
      ElMessage.success('项目更新成功')
      return res.data
    } catch {
      ElMessage.error('更新项目失败')
    }
  }

  async function removeProject(id) {
    try {
      await deleteProjectApi(id)
      projects.value = projects.value.filter(p => p.id !== id)
      if (currentProject.value?.id === id) currentProject.value = null
      ElMessage.success('项目已删除')
    } catch {
      ElMessage.error('删除项目失败')
    }
  }

  async function uploadTender(id, formData) {
    try {
      const res = await uploadTenderApi(id, formData)
      return res.data
    } catch (error) {
      ElMessage.error(error.message || '文件上传失败')
      throw error
    }
  }

  async function fetchTenderDocs(projectId) {
    try {
      const res = await listTenderDocumentsApi(projectId)
      tenderDocs.value = parseArray(res)
    } catch (error) {
      ElMessage.error(error.message || '获取招标文件列表失败')
    }
  }

  async function removeTenderDoc(docId) {
    try {
      await deleteTenderDocumentApi(docId)
      tenderDocs.value = tenderDocs.value.filter(d => d.id !== docId)
      ElMessage.success('招标文件已删除')
    } catch {
      ElMessage.error('删除招标文件失败')
    }
  }

  function normalizeRequirement(item) {
    return {
      id: item.id,
      project_id: item.project_id,
      tender_document_id: item.tender_document_id,
      category: item.category,
      content: item.content,
      source_text: item.source_text,
      source_ref: item.source_ref,
      priority: item.priority,
      status: item.status,
      assignee_id: item.assignee_id,
      risk_level: item.risk_level,
      response_status: item.response_status || null,
      has_response: item.has_response || false,
      created_at: item.created_at,
      updated_at: item.updated_at,
    }
  }

  async function fetchRequirements(projectId, params = {}) {
    try {
      const res = await getRequirementsApi(projectId, params)
      const list = parseArray(res)
      requirements.value = list.map(normalizeRequirement)
      return requirements.value
    } catch (error) {
      ElMessage.error(error.message || '获取需求项列表失败')
      return []
    }
  }

  async function updateRequirementStatus(reqId, updates) {
    try {
      const res = await updateRequirementApi(reqId, updates)
      const idx = requirements.value.findIndex(r => r.id === reqId)
      if (idx !== -1) {
        requirements.value[idx] = { ...requirements.value[idx], ...updates }
      }
      if (currentProject.value?.requirements) {
        const reqIdx = currentProject.value.requirements.findIndex(r => r.id === reqId)
        if (reqIdx !== -1) {
          currentProject.value.requirements[reqIdx] = { ...currentProject.value.requirements[reqIdx], ...updates }
        }
      }
      return true
    } catch {
      ElMessage.error('更新需求项状态失败')
      return false
    }
  }

  async function parseDocument(docId) {
    parseLoading.value = true
    try {
      const res = await parseTenderDocumentApi(docId)
      const data = parseResponse(res, {})
      ElMessage.success(`解析完成，提取了 ${data.requirement_count || 0} 条需求项`)
      return data
    } catch (error) {
      ElMessage.error(error.response?.data?.message || '解析失败')
      throw error
    } finally {
      parseLoading.value = false
    }
  }

  return {
    projects,
    currentProject,
    requirements,
    tenderDocs,
    loading,
    parseLoading,
    filters,
    totalProjects,
    filteredProjects,
    stats,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    removeProject,
    uploadTender,
    fetchTenderDocs,
    removeTenderDoc,
    fetchRequirements,
    updateRequirementStatus,
    parseDocument,
    setMatchAnalysis
  }
})
