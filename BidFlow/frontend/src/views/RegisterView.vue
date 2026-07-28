<!-- RegisterView.vue - Registration page (redirects to LoginView) -->
<template>
  <!-- Registration is handled within LoginView via isLogin toggle -->
  <LoginView />
</template>

<script setup>
import LoginView from './LoginView.vue'
</script>
