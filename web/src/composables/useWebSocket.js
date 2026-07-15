import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { wsUrl } from '@/api/client'

export function useWebSocket(onMessage) {
  const ws = ref(null)
  const auth = useAuthStore()

  function connect() {
    if (!auth.token) return
    const url = wsUrl(auth.token)
    ws.value = new WebSocket(url)
    ws.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage(data)
      } catch (e) {
        console.error('WS parse error', e)
      }
    }
    ws.value.onclose = () => {
      setTimeout(connect, 3000)
    }
  }

  function disconnect() {
    if (ws.value) {
      ws.value.close()
    }
  }

  onMounted(connect)
  onUnmounted(disconnect)

  return { connect, disconnect }
}
