<template><button @click="submit">Run</button></template>
<script setup lang="ts">
import { helper } from '@/helpers'
function submit() { return helper() }
</script>
