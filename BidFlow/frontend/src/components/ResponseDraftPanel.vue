<!-- ResponseDraftPanel.vue - Draft response panel for requirement AI generation -->
<template>
  <el-drawer
    v-model="visible"
    title="响应草案"
    :size="drawerSize"
    :before-close="handleClose"
    destroy-on-close
  >
    <div v-if="currentReq" class="draft-panel">
      <!-- Requirement info -->
      <div class="draft-req-info">
        <h3>{{ currentReq.title }}</h3>
        <p class="req-desc">{{ currentReq.description }}</p>
        <div class="req-meta">
          <el-tag size="small">{{ getCategoryLabel(currentReq.category) }}</el-tag>
          <el-tag size="small" :type="getPriorityType(currentReq.priority)">{{ currentReq.priority }}</el-tag>
        </div>
      </div>

      <!-- Draft content (flex:1 撑满剩余高度，独立滚动) -->
      <div class="draft-content">
        <div class="draft-header">
          <span>响应草案内容</span>
          <el-tag v-if="draftStatus === 'drafting'" type="primary" effect="light" size="small">
            <template #icon><span class="material-symbols-outlined animate-spin">progress_activity</span></template>
            生成中...
          </el-tag>
          <el-tag v-else-if="contentLoading" type="info" effect="light" size="small">
            <template #icon><span class="material-symbols-outlined animate-spin">progress_activity</span></template>
            加载中...
          </el-tag>
        </div>
        <!-- 加载中显示骨架/提示，不渲染空 textarea（避免"有内容却显示空"的误解） -->
        <div v-if="contentLoading" class="draft-loading">
          <span class="material-symbols-outlined animate-spin">progress_activity</span>
          <span>正在加载响应草案...</span>
        </div>
        <el-input
          v-else
          v-model="draftContent"
          type="textarea"
          :rows="editorRows"
          placeholder="在此输入或编辑响应内容（点「重新生成」可让 AI 重写）..."
          :disabled="draftStatus === 'drafting'"
          :aria-label="'响应草案内容-' + (currentReq.id || '')"
          class="draft-textarea"
        />
        <div class="draft-sources" v-if="sources.length">
          <span class="sources-label">参考资料：</span>
          <div v-for="(src, i) in sources" :key="i" class="source-item">
            <span class="material-symbols-outlined text-primary">description</span>
            <div class="source-body">
              <div class="source-head">
                <span class="source-text">{{ sourceName(src) }}</span>
                <el-tag v-if="sourceScore(src) != null" size="small" :type="scoreType(sourceScore(src))">
                  相关度 {{ Number(sourceScore(src)).toFixed(2) }}
                </el-tag>
              </div>
              <span class="source-preview" v-if="sourcePreview(src)">{{ sourcePreview(src) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部固定操作栏（审核流核心操作常驻） -->
      <div class="draft-footer">
        <div class="draft-status">
          <label>审核状态</label>
          <el-select v-model="status" placeholder="请选择审核状态" size="default" @change="handleStatusChange" :key="selectKey">
            <el-option
              v-for="opt in STATUS_OPTIONS"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <div class="draft-actions">
          <el-button @click="regenerate" :loading="draftStatus === 'drafting'">
            <template #icon><span class="material-symbols-outlined">refresh</span></template>
            重新生成
          </el-button>
          <el-button type="primary" @click="saveDraft" :loading="saving">
            <template #icon><span class="material-symbols-outlined">save</span></template>
            保存草案
          </el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  requirement: { type: Object, default: null }
})

const emit = defineEmits(['update:modelValue', 'save', 'regenerate', 'status-change'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const currentReq = computed(() => props.requirement)
const draftContent = ref('')
const draftStatus = ref('idle')
const saving = ref(false)
const status = ref('editing')
const sources = ref([])

// 抽屉响应式宽度：小屏全屏，桌面端占 55-62%，大屏 52%
const drawerSize = computed(() => {
  const w = window.innerWidth
  if (w <= 768) return '100%'
  if (w <= 1280) return '62%'
  if (w <= 1920) return '55%'
  return '52%'
})

// 文本框行数：桌面端 20 行（审核舒适），小屏 14 行
const editorRows = computed(() => (window.innerWidth <= 1280 ? 14 : 20))

const STATUS_OPTIONS = [
  { label: '待编辑', value: 'editing' },
  { label: '待审核', value: 'review' },
  { label: '已批准', value: 'approved' },
  { label: '已驳回', value: 'rejected' },
]

const STATUS_MAP = {
  'editing': 'editing',
  'review': 'review',
  'approved': 'approved',
  'rejected': 'rejected',
  '草稿': 'editing',
  'pending_review': 'review',
  'needs_manual': 'editing',
  'completed': 'approved',
  'pending': 'editing',
}

function mapStatusFromBackend(s) {
  return STATUS_MAP[s] || 'editing'
}

const selectKey = ref(0)  // 状态变化时强制 el-select 重新渲染，确保显示匹配项
const contentLoading = ref(false)  // 内容加载中（父组件 _loading 标记）

// 只监听 requirement.id（方案 A）：切换需求才重置内容，避免父组件 await 返回时
// 重新赋值对象触发 deep watch 造成的"清空 → 加载 → 填充"空闪
// + loading 保护（方案 C）：_loading=true 时显示加载中，不清空 draftContent
watch(() => props.requirement?.id, (id) => {
  if (!id) return
  const req = props.requirement
  if (req?._loading) {
    contentLoading.value = true   // 显示加载中，不重置内容
    return
  }
  contentLoading.value = false
  draftContent.value = req?._draftContent || ''
  sources.value = req?._sources || []
  status.value = mapStatusFromBackend(req?._status || req?.status || '')
  draftStatus.value = 'idle'
  saving.value = false
  selectKey.value++  // 强制 el-select 重新渲染，让 status 匹配项正确显示
}, { immediate: true })

// 兜底：_loading 生命周期（父组件 _loading=true → 显示加载中骨架；finally false → 刷新内容）
// 覆盖「重新生成」场景：id 不变，只能靠此 watch 感知生成开始（true）与结束（false）
watch(() => props.requirement?._loading, (loading) => {
  if (loading === true) {
    contentLoading.value = true   // 生成/加载中：显示骨架，不重置已编辑内容
    return
  }
  if (loading === false && props.requirement?.id) {
    const req = props.requirement
    contentLoading.value = false
    draftContent.value = req?._draftContent || ''
    sources.value = req?._sources || []
    status.value = mapStatusFromBackend(req?._status || req?.status || '')
    draftStatus.value = 'idle'   // 复位 regenerate() 设置的 drafting（重新生成结束）
    saving.value = false
    selectKey.value++
  }
})

// 内容变化监听（「重新生成」按钮路径：id 不变但 _draftContent 被父组件更新）
// 只更新 draftContent，不重置 sources/status/selectKey，避免打断用户操作
// L10：父组件保存成功后写回 _draftContent → 此处复位 saving（替代 1.2s 硬编码定时器）
watch(() => props.requirement?._draftContent, (content) => {
  if (!contentLoading.value && props.requirement?.id) {
    draftContent.value = content || ''
    saving.value = false
  }
})

watch(visible, (val) => {
  if (!val) {
    draftStatus.value = 'idle'
    saving.value = false
  }
})

function getCategoryLabel(cat) {
  const map = { technical: '技术', business: '商务', qualification: '资质', scoring: '评分', 技术: '技术', 商务: '商务', 资格: '资质', 评分: '评分' }
  return map[cat] || cat
}

// 溯源展示辅助：兼容 string（旧数据）与 object（含 filename/content/score/source_ref）
function sourceName(src) {
  if (typeof src === 'string') return src
  return src?.filename || src?.source || src?.source_ref || '未知来源'
}
function sourceScore(src) {
  if (typeof src === 'string') return null
  const s = src?.rerank_score ?? src?.score
  return typeof s === 'number' ? s : null
}
function sourcePreview(src) {
  if (typeof src === 'string') return ''
  const c = src?.content || src?.quote || ''
  return c ? c.slice(0, 60) : ''
}
function scoreType(score) {
  if (score >= 0.6) return 'success'
  if (score >= 0.3) return 'warning'
  return 'danger'
}

function getPriorityType(p) {
  const map = { p0: 'danger', p1: 'warning', p2: '', P0: 'danger', P1: 'warning', P2: '' }
  return map[p] || ''
}

function regenerate() {
  draftStatus.value = 'drafting'
  emit('regenerate')
}

async function saveDraft() {
  if (saving.value) return
  if (!draftContent.value.trim()) {
    ElMessage.warning('请输入响应内容')
    return
  }
  saving.value = true
  // L10：保存成功由父组件写回 _draftContent 触发 watch 复位 saving（去掉 1.2s 硬编码）；
  // 父组件失败时由下面 catch 复位
  try {
    emit('save', draftContent.value)
  } catch (e) {
    saving.value = false
    ElMessage.error(e.message || '保存失败')
  }
}

function handleStatusChange(val) {
  // L5：切状态时携带当前编辑内容——避免"改完未点保存就切状态 → 编辑内容丢失"
  emit('status-change', { status: val, content: draftContent.value })
}

function handleClose(done) {
  done()
}
</script>

<style scoped>
/* 抽屉 body 用 flex 纵向布局：信息卡 + 正文区 + 固定底部操作栏 */
:deep(.el-drawer__body) {
  display: flex;
  flex-direction: column;
  padding: 20px;
  min-height: 0;
}

.draft-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.draft-req-info {
  padding: 16px;
  background: var(--surface-container-low);
  border-radius: 12px;
  flex-shrink: 0;
}

.draft-req-info h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--on-surface);
  margin-bottom: 8px;
}

/* P1-2：需求描述 3 行截断，避免撑爆布局 */
.draft-req-info .req-desc {
  font-size: 15px;
  color: var(--on-surface-variant);
  line-height: 1.6;
  margin-bottom: 12px;
  max-height: 72px;
  overflow-y: auto;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  word-break: break-word;
}

.req-meta {
  display: flex;
  gap: 8px;
}

/* P2-1：正文区 flex:1 撑满剩余高度，独立滚动 */
.draft-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.draft-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--on-surface);
}

/* 内容加载中占位（与 textarea 同尺寸，避免抽屉跳动） */
.draft-loading {
  flex: 1;
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 14px;
  color: var(--on-surface-variant);
  background: var(--surface-container-low);
  border-radius: 12px;
}

/* 文本框撑满 + 字号加大（审核可读性） */
.draft-textarea {
  flex: 1;
  min-height: 320px;
}
.draft-textarea :deep(.el-textarea__inner) {
  border-radius: 12px;
  font-family: inherit;
  font-size: 15px;
  line-height: 1.8;
  height: 100% !important;
}

.draft-sources {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
}

.sources-label {
  font-size: 12px;
  color: var(--outline);
  font-weight: 600;
}

/* P2-2：长文件名可换行，避免横向溢出 */
.source-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  color: var(--on-surface-variant);
}
.source-item .source-text {
  word-break: break-all;
  line-height: 1.5;
  min-width: 0;
}

/* RAG 增强：来源卡片——文件名 + 相关度 + 片段摘要 */
.source-body { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.source-head { display: flex; align-items: center; gap: 8px; }
.source-head .source-text { font-weight: 500; color: var(--on-surface); }
.source-preview {
  font-size: 12px;
  color: var(--outline);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.5;
}

.text-primary { color: var(--primary); }

/* P1-1：底部固定操作栏——审核流核心操作常驻可视 */
.draft-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-top: 14px;
  border-top: 1px solid var(--border-subtle);
  flex-shrink: 0;
}

.draft-status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.draft-status label {
  font-size: 14px;
  font-weight: 600;
  color: var(--on-surface);
  white-space: nowrap;
}

.draft-status .el-select {
  min-width: 180px;
  flex-shrink: 0;
}

.draft-actions {
  display: flex;
  gap: 10px;
  flex-shrink: 0;
}

/* Animation */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.animate-spin {
  animation: spin 1s linear infinite;
}
</style>
