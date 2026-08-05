// usePagination - Composable for pagination logic
// Used by ProjectListView, CompanyMaterialsView, and any paginated list

import { ref, computed } from 'vue'

/**
 * @param {number} [pageSize=10] - Number of items per page
 * @param {import('vue').Ref<Array>} [items] - Reactive array of all items (optional)
 */
export function usePagination(pageSize = 10, items = null) {
  const currentPage = ref(1)
  const size = ref(pageSize)

  /**
   * Get paged slice from a source array
   * @param {Array} source - Full array to paginate
   * @returns {Array} Current page's items
   */
  function paged(source) {
    const start = (currentPage.value - 1) * size.value
    return source.slice(start, start + size.value)
  }

  /**
   * Auto-paginate from the provided reactive items ref
   */
  const pagedItems = computed(() => {
    if (!items?.value) return []
    return paged(items.value)
  })

  /**
   * Range display text: "显示 X-Y 共 Z 条"
   * @param {number} total - Total count
   * @returns {string}
   */
  function rangeText(total) {
    if (!total) return '显示 0-0 共 0 条'
    const start = (currentPage.value - 1) * size.value + 1
    const end = Math.min(currentPage.value * size.value, total)
    return `显示 ${start}-${end} 共 ${total} 条`
  }

  /**
   * Reset to page 1
   */
  function reset() {
    currentPage.value = 1
  }

  /**
   * Go to specific page (clamped to valid range)
   */
  function goTo(page, totalItems) {
    const maxPage = Math.max(1, Math.ceil(totalItems / size.value))
    currentPage.value = Math.max(1, Math.min(page, maxPage))
  }

  return {
    currentPage,
    pageSize: size,
    paged,
    pagedItems,
    rangeText,
    reset,
    goTo
  }
}