<!-- ResponseDraftPanel.vue - Draft response panel for requirement AI generation -->
<template>
  <el-drawer
    v-model="visible"
    title="响应草案"
    size="600px"
    :before-close="handleClose"
  >
    <div v-if="currentReq" class="draft-panel">
      <!-- Requirement info -->
      <div class="draft-req-info">
        <h3>{{ currentReq.title }}</h3>
        <p>{{ currentReq.description }}</p>
        <div class="req-meta">
          <el-tag size="small">{{ getCategoryLabel(currentReq.category) }}</el-tag>
          <el-tag size="small" :type="getPriorityType(currentReq.priority)">{{ currentReq.priority }}</el-tag>
        </div>
      </div>

      <!-- Draft content -->
      <div class="draft-content">
        <div class="draft-header">
          <span>AI 生成的响应草案</span>
          <el-tag v-if="draftStatus === 'drafting'" type="primary" effect="light" size="small">
            <template #icon><span class="material-symbols-outlined animate-spin">progress_activity</span></template>
            生成中...
          </el-tag>
        </div>
        <el-input
          v-model="draftContent"
          type="textarea"
          :rows="10"
          placeholder="AI 正在生成响应草案..."
          :disabled="draftStatus === 'drafting'"
          class="draft-textarea"
        />
        <div class="draft-sources" v-if="sources.length">
          <span class="sources-label">参考资料：</span>
          <div v-for="(src, i) in sources" :key="i" class="source-item">
            <span class="material-symbols-outlined text-primary">description</span>
            <span>{{ src }}</span>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="draft-actions">
        <el-button @click="regenerate" :loading="draftStatus === 'drafting'">
          <template #icon><span class="material-symbols-outlined">refresh</span></template>
          重新生成
        </el-button>
        <el-button type="primary" @click="saveDraft">
          <template #icon><span class="material-symbols-outlined">save</span></template>
          保存草案
        </el-button>
      </div>

      <!-- Status update -->
      <div class="draft-status">
        <label>审核状态</label>
        <el-select v-model="status" size="default" @change="handleStatusChange">
          <el-option label="待编辑" value="editing" />
          <el-option label="待审核" value="review" />
          <el-option label="已批准" value="approved" />
          <el-option label="已驳回" value="rejected" />
        </el-select>
      </div>
    </div>
  </el-drawer>
</template>

<script setup>
import { ref, computed } from 'vue'
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
const status = ref('editing')
const sources = ref([])

function getCategoryLabel(cat) {
  const map = { technical: '技术', business: '商务', qualification: '资质', scoring: '评分' }
  return map[cat] || cat
}

function getPriorityType(p) {
  const map = { p0: 'danger', p1: 'warning', p2: '' }
  return map[p] || ''
}

function regenerate() {
  draftStatus.value = 'drafting'
  draftContent.value = ''
  setTimeout(() => {
    draftContent.value = '根据招标文件要求，我方承诺完全响应该条款。具体方案如下：\n\n1. 资质方面：我方具备相关要求的全部资质证书\n2. 技术方面：采用行业领先的技术方案\n3. 商务方面：报价合理，条款响应无偏差'
    sources.value = ['企业资质证书.pdf', '技术方案.docx']
    draftStatus.value = 'idle'
    ElMessage.success('草案生成完成')
    emit('regenerate')
  }, 1500)
}

function saveDraft() {
  if (!draftContent.value.trim()) {
    ElMessage.warning('请输入响应内容')
    return
  }
  emit('save', draftContent.value)
  ElMessage.success('草案已保存')
}

function handleStatusChange(val) {
  emit('status-change', val)
}

function handleClose(done) {
  done()
}
</script>

<style scoped>
.draft-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.draft-req-info {
  padding: 16px;
  background: var(--surface-container-low);
  border-radius: 12px;
}

.draft-req-info h3 {
  font-size: 16px;
  font-weight: 600;
  color: var(--on-surface);
  margin-bottom: 8px;
}

.draft-req-info p {
  font-size: 14px;
  color: var(--on-surface-variant);
  line-height: 1.6;
  margin-bottom: 12px;
}

.req-meta {
  display: flex;
  gap: 8px;
}

.draft-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.draft-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--on-surface);
}

.draft-textarea :deep(.el-textarea__inner) {
  border-radius: 12px;
  font-family: inherit;
  line-height: 1.7;
}

.draft-sources {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sources-label {
  font-size: 12px;
  color: var(--outline);
  font-weight: 600;
}

.source-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--on-surface-variant);
}

.text-primary { color: var(--primary); }

.draft-actions {
  display: flex;
  gap: 12px;
}

.draft-status {
  display: flex;
  align-items: center;
  gap: 12px;
}

.draft-status label {
  font-size: 14px;
  font-weight: 600;
  color: var(--on-surface);
  white-space: nowrap;
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
