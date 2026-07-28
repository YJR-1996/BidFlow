<!-- App.vue - Root component with auth-based layout switching -->
<template>
  <router-view />
</template>

<script setup>
// Layout is determined by router: unauthenticated pages render directly,
// authenticated pages are wrapped in AppLayout via nested routes.
</script>
