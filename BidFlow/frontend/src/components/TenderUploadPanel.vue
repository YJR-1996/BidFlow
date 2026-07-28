<!-- TenderUploadPanel.vue - Tender document upload with validation -->
<template>
  <div class="upload-panel">
    <h3 class="panel-title">
      <span class="material-symbols-outlined text-primary">cloud_upload</span>
      上传招标文件
    </h3>

    <el-upload
      drag
      :auto-upload="false"
      :on-change="handleChange"
      :on-remove="handleRemove"
      :file-list="fileList"
      multiple
      accept=".pdf,.docx,.txt"
      :limit="5"
      class="upload-zone"
    >
      <span class="material-symbols-outlined upload-icon">cloud_upload</span>
      <p class="upload-title">点击或拖拽文件到此处上传</p>
      <p class="upload-hint">支持格式：PDF, DOCX, TXT (限 25MB，最多 5 个文件)</p>
    </el-upload>

    <div v-if="fileList.length" class="file-list">
      <div v-for="(file, index) in fileList" :key="file.uid" class="file-item">
        <span class="material-symbols-outlined" :class="file.status === 'done' ? 'text-success-green' : 'text-primary'">
          {{ file.status === 'done' ? 'check_circle' : 'upload_file' }}
        </span>
        <div class="file-info">
          <span class="file-name">{{ file.name }}</span>
          <span class="file-size">{{ formatSize(file.size) }}</span>
        </div>
        <div v-if="file.status === 'uploading'" class="file-progress">
          <el-progress :percentage="file.percent || 0" :stroke-width="6" />
        </div>
        <span v-if="file.status === 'error'" class="file-error">上传失败</span>
        <el-button
          v-if="file.status === 'done'"
          size="small"
          text
          @click="$emit('parse-complete', index)"
        >
          <template #icon><span class="material-symbols-outlined">sync</span></template>
          刷新
        </el-button>
      </div>
    </div>

    <div v-if="errorMsg" class="upload-error">
      <span class="material-symbols-outlined">error</span>
      {{ errorMsg }}
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

const emit = defineEmits(['parse-complete'])

const fileList = ref([])
const errorMsg = ref('')

const allowedTypes = ['application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain']
const allowedExtensions = ['.pdf', '.docx', '.txt']
const maxFileSize = 25 * 1024 * 1024 // 25MB

function validateFile(file) {
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!allowedExtensions.includes(ext)) {
    errorMsg.value = `不支持的文件格式：${ext}。请上传 PDF、DOCX 或 TXT 文件。`
    return false
  }
  if (file.size > maxFileSize) {
    errorMsg.value = `文件过大：${file.name}。文件大小不能超过 25MB。`
    return false
  }
  errorMsg.value = ''
  return true
}

function handleChange(file, files) {
  if (!validateFile(file.raw)) return
  fileList.value = files.map(f => ({
    uid: f.uid,
    name: f.name,
    size: f.size,
    status: 'uploading',
    percent: 0
  }))

  // Simulate upload
  simulateUpload(files[files.length - 1].raw)
}

function handleRemove(file) {
  fileList.value = fileList.value.filter(f => f.uid !== file.uid)
}

function simulateUpload(file) {
  let percent = 0
  const interval = setInterval(() => {
    percent += Math.random() * 15 + 5
    if (percent >= 100) {
      percent = 100
      clearInterval(interval)
      const f = fileList.value.find(f => f.name === file.name)
      if (f) {
        f.status = 'done'
        f.percent = 100
      }
      ElMessage.success(`${file.name} 上传成功，正在解析...`)
      // Notify parent after "parsing" completes
      setTimeout(() => {
        // emit parse-complete to parent
      }, 2000)
    } else {
      const f = fileList.value.find(f => f.name === file.name && f.status === 'uploading')
      if (f) f.percent = Math.floor(percent)
    }
  }, 300)
}

function formatSize(bytes) {
  if (!bytes) return ''
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`
}
</script>

<style scoped>
.upload-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--on-surface);
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.text-primary { color: var(--primary); }

.upload-zone :deep(.el-upload-dragger) {
  border-radius: 12px;
  padding: 40px 16px;
  border-color: var(--outline-variant);
}

.upload-zone :deep(.el-upload-dragger:hover) {
  border-color: var(--primary);
  background: var(--surface-container-low);
}

.upload-icon {
  font-size: 48px;
  color: var(--outline);
}

.upload-title {
  font-size: 14px;
  font-weight: 600;
  margin: 8px 0 4px;
}

.upload-hint {
  font-size: 12px;
  color: var(--outline);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--surface-container-low);
  border-radius: 8px;
}

.file-item .material-symbols-outlined {
  font-size: 24px;
}

.text-success-green { color: #34a853; }

.file-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-size: 14px;
  font-weight: 500;
}

.file-size {
  font-size: 12px;
  color: var(--outline);
}

.file-progress {
  width: 120px;
}

.file-error {
  font-size: 12px;
  color: var(--error);
  font-weight: 600;
}

.upload-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--error-container) / 0.2;
  border: 1px solid var(--error) / 0.2;
  border-radius: 8px;
  color: var(--error);
  font-size: 14px;
}

.upload-error .material-symbols-outlined {
  font-size: 20px;
}
</style>
