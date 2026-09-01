# App Boot Loading Design

The application shell remains cloaked until the initial agent, chat, health,
resource, route, and Lucide setup sequence finishes. A lightweight, themed
daisyUI `loading loading-bars` boot shell is visible from the first HTML paint
and disappears only when the workspace is ready. Subsequent page navigation
continues to use its existing inline loading states.
