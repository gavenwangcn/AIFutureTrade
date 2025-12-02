<template>
  <div v-if="visible" class="modal show" @click.self="handleClose">
    <div class="modal-content" :class="{ large: large }">
      <div class="modal-header">
        <div>
          <h3>{{ title }}</h3>
          <p v-if="subtitle" class="modal-subtitle">{{ subtitle }}</p>
        </div>
        <button class="btn-close" @click="handleClose">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="modal-body">
        <slot></slot>
      </div>
      <div v-if="$slots.footer" class="modal-footer">
        <slot name="footer"></slot>
      </div>
    </div>
  </div>
</template>

<script setup>
import { watch } from 'vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  title: {
    type: String,
    required: true
  },
  subtitle: {
    type: String,
    default: ''
  },
  large: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'close'])

const handleClose = () => {
  emit('update:visible', false)
  emit('close')
}

// 监听 visible 变化，防止 body 滚动
watch(() => props.visible, (newVal) => {
  if (newVal) {
    document.body.style.overflow = 'hidden'
  } else {
    document.body.style.overflow = ''
  }
})
</script>

<style scoped>
.modal-content.large {
  width: 800px;
  max-width: 95vw;
}

.modal-subtitle {
  font-size: 13px;
  color: var(--text-3);
  margin-top: 4px;
}
</style>

