function platform() {
  return {
    settingsOpen: false,
    settingsTab: "general",
    language: localStorage.getItem("oma-language") || "en",
    timezone: localStorage.getItem("oma-timezone") || "Asia/Shanghai",
    themePreference: ["system", "light", "dark"].includes(
      localStorage.getItem("oma-theme-preference"),
    )
      ? localStorage.getItem("oma-theme-preference")
      : "system",
    runError: "",
    mobileSidebarOpen: false,
    linkDrawerOpen: false,
    linkDrawerTitle: "",
    linkDrawerItems: [],
    webActivities: Object.create(null),
    autopilots: [],
    autopilotSearch: "",
    autopilotAgentFilter: "",
    autopilotAgentPickerOpen: false,
    autopilotDialog: null,
    autopilotRuns: [],
    autopilotRunsOpen: false,
    autopilotRunsItem: null,
    autopilotLoading: false,
    autopilotSaving: false,
    autopilotEditing: null,
    autopilotName: "",
    autopilotInstruction: "",
    autopilotAgentId: "",
    autopilotCron: "0 * * * *",
    autopilotStartsAt: "",
    autopilotEndsAt: "",
    autopilotDeleteTarget: null,
    cronBuilderOpen: false,
    cronFrequency: "hourly",
    cronDay: ["1"],
    cronHour: "9",
    cronMinute: "0",
    cronMonth: "1",
    cronDayOfMonth: "1",
    page: "chat",
    agents: [],
    chats: [],
    activeChat: null,
    editingChatTitle: false,
    chatTitleDraft: "",
    chatTitleSaving: false,
    messages: [],
    selectedAgentId: "",
    sidebarCollapsed: false,
    agentPickerOpen: false,
    activeProcesses: 0,
    draft: "",
    loading: false,
    watchingChat: null,
    streamSource: null,
    pollTimer: null,
    sharedMode: false,
    sharedToken: "",
    shareMode: false,
    shareStep: null,
    shareUrl: "",
    creatingShare: false,
    copiedShare: false,
    copiedKey: "",
    feedback: {},
    messagesLoading: false,
    sessionUsage: {
      input: 0,
      output: 0,
      cacheRead: 0,
      cost: 0,
      search: 0,
      fetch: 0,
    },
    reasoningOpen: Object.create(null),
    filesOpen: false,
    filesLoading: false,
    files: [],
    fileViewer: null,
    libraryFiles: [],
    libraryLoading: false,
    librarySearch: "",
    libraryAgentFilter: "",
    libraryAgentPickerOpen: false,
    libraryPage: 1,
    libraryPages: 1,
    libraryTotal: 0,
    marketTab: "skills",
    marketCatalogSearch: "",
    marketInstallOpen: false,
    marketSearch: "",
    marketOwner: "",
    marketSearchResults: [],
    marketSearchLoading: false,
    marketSearchError: "",
    marketActionSkill: "",
    marketExtensionPackage: "",
    marketExtensionAction: false,
    marketUninstallTarget: null,
    toastMessage: "",
    toastKind: "success",
    authChecked: false,
    authUser: null,
    loginUsername: "",
    loginPassword: "",
    loginLoading: false,
    loginError: "",
    usersOpen: false,
    users: [],
    usersLoading: false,
    userAddOpen: false,
    userCreating: false,
    userDeleteTarget: null,
    logoutConfirmOpen: false,
    newUserUsername: "",
    newUserEmail: "",
    searchOpen: false,
    chatSearchQuery: "",
    chatSearchAgentFilter: "",
    chatSearchAgentPickerOpen: false,
    error: "",
    dialog: null,
    confirmTarget: null,
    deleteChatTarget: null,
    editingAgent: null,
    createDialog: false,
    creating: false,
    newAgentName: "",
    newAgentInstruction: "",
    newAgentAvatarFile: null,
    newAgentAvatarPreview: "",
    newAgentProvider: "",
    newAgentModel: "",
    newAgentThinkingLevel: "",
    newAgentTools: [],
    newAgentExtensions: [],
    newAgentSkills: [],
    newAgentMcpServers: [],
    mode: ["development", "production"].includes(
      new URLSearchParams(location.search).get("mode"),
    )
      ? new URLSearchParams(location.search).get("mode")
      : "production",
    resources: {
      extensions: [],
      skills: [],
      mcp_servers: [],
      providers: [],
      default_tools: [],
      default_extensions: [],
      default_skills: [],
      default_mcp_servers: [],
      mode: "production",
      default_thinking_level: "low",
    },
    toolCatalog: [
      { name: "read", description: "Read file contents" },
      { name: "write", description: "Create or overwrite files" },
      { name: "edit", description: "Patch files with find/replace" },
      { name: "bash", description: "Run shell commands" },
      { name: "grep", description: "Search file contents" },
      { name: "find", description: "Find files by glob" },
      { name: "ls", description: "List directory contents" },
    ],
    theme: ["light", "dark"].includes(localStorage.getItem("pi-theme"))
      ? localStorage.getItem("pi-theme")
      : "light",
    appReady: false,
    async init() {
      window.omaPlatform = this;
      this.sharedMode =
        window.location.pathname.startsWith("/share/") ||
        window.location.pathname === "/file-view" ||
        new URLSearchParams(location.search).has("share");
      if (this.sharedMode) this.authChecked = true;
      this.setTheme(this.theme);
      if (!this.sharedMode) {
        await this.loadSession();
        if (!this.authUser) {
          this.appReady = true;
          return;
        }
      }
      try {
        this.feedback = JSON.parse(
          localStorage.getItem("oma-feedback") || "{}",
        );
      } catch {
        this.feedback = {};
      }
      window.addEventListener("popstate", () => this.routeFromUrl());
      try {
        if (this.sharedMode) {
          // Public share view: the regular workspace APIs are auth-gated, so
          // only the token-gated share payload is fetched.
          await this.routeFromUrl();
          return;
        }
        await Promise.all([
          this.loadAgents(),
          this.loadChats(),
          this.loadHealth(),
          this.loadResources(),
        ]);
        if (this.agents.length) this.selectedAgentId = this.agents[0].id;
        if (!new URLSearchParams(location.search).has("mode"))
          this.mode = this.resources.mode || "production";
        setInterval(() => this.loadHealth(), 5000);
        await this.routeFromUrl();
      } catch (e) {
        this.showError(e);
      } finally {
        this.renderIcons();
        this.observeIcons();
        this.appReady = true;
      }
    },
    renderIcons() {
      if (window.lucide?.createIcons) window.lucide.createIcons();
    },
    observeIcons() {
      if (!window.MutationObserver) return;
      const observer = new MutationObserver((mutations) => {
        const hasIcons = mutations.some((mutation) =>
          [...mutation.addedNodes].some(
            (node) =>
              node.nodeType === Node.ELEMENT_NODE &&
              node.tagName?.toLowerCase() !== "svg" &&
              (node.matches?.("[data-lucide]") ||
                node.querySelector?.("[data-lucide]")),
          ),
        );
        if (hasIcons) this.renderIcons();
      });
      observer.observe(document.body, { childList: true, subtree: true });
    },
    async api(path, options = {}) {
      const requestPath =
        path.includes("/messages") && !path.includes("?")
          ? `${path}?mode=${this.mode}`
          : path;
      const requestId = crypto.randomUUID();
      const headers = new Headers(options.headers || {});
      headers.set("Content-Type", "application/json");
      headers.set("X-Request-ID", requestId);
      const response = await fetch(requestPath, {
        ...options,
        headers,
      });
      const responseId = response.headers.get("X-Request-ID") || requestId;
      const contentType = response.headers.get("content-type") || "";
      let data = null;
      if (contentType.includes("json")) {
        try {
          data = await response.json();
        } catch {
          data = null;
        }
      } else {
        await response.text();
      }
      if (!response.ok) {
        throw this.errorFromResponse(response, responseId, data);
      }
      if (data === null) {
        const error = new Error(
          `Server returned a non-JSON response (request_id: ${responseId})`,
        );
        error.requestId = responseId;
        throw error;
      }
      return data;
    },
    async loadSession() {
      try {
        const data = await this.api("/api/auth/session");
        this.authUser = data.user;
      } catch (error) {
        this.authUser = null;
        this.loginError = error.message;
      } finally {
        this.authChecked = true;
      }
    },
    async login() {
      if (this.loginLoading) return;
      this.loginLoading = true;
      this.loginError = "";
      try {
        this.authUser = await this.api("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({
            username: this.loginUsername,
            password: this.loginPassword,
          }),
        });
        this.loginPassword = "";
        this.appReady = false;
        await Promise.all([
          this.loadAgents(),
          this.loadChats(),
          this.loadHealth(),
          this.loadResources(),
        ]);
        if (this.agents.length) this.selectedAgentId = this.agents[0].id;
        this.appReady = true;
        await this.routeFromUrl();
      } catch (error) {
        this.authUser = null;
        this.loginError = error.message;
      } finally {
        this.loginLoading = false;
      }
    },
    requestLogout() {
      this.logoutConfirmOpen = true;
    },
    async confirmLogout() {
      try {
        await this.api("/api/auth/logout", { method: "POST" });
        this.logoutConfirmOpen = false;
        this.usersOpen = false;
        this.authUser = null;
        this.authChecked = true;
        this.appReady = true;
        this.page = "chat";
      } catch (error) {
        this.showError(error);
      }
    },
    errorFromResponse(response, requestId, data = null) {
      const detail = data?.detail || `Server returned ${response.status}`;
      const error = new Error(`${detail} (request_id: ${requestId})`);
      error.requestId = requestId;
      return error;
    },
    async loadAgents() {
      try {
        await this.refreshAgents();
      } catch (e) {
        this.showError(e);
      }
    },
    async refreshAgents() {
      const data = await this.api("/api/agents");
      this.agents = data.agents || [];
      return this.agents;
    },
    async loadUsers() {
      this.usersLoading = true;
      try {
        this.users = (await this.api("/api/users")).users;
      } catch (error) {
        this.showError(error);
      } finally {
        this.usersLoading = false;
      }
    },
    async openUsers() {
      this.usersOpen = true;
      await this.loadUsers();
    },
    openAddUser() {
      this.newUserUsername = "";
      this.newUserEmail = "";
      this.userAddOpen = true;
    },
    async createManagedUser() {
      if (this.userCreating) return;
      this.userCreating = true;
      try {
        await this.api("/api/users", {
          method: "POST",
          body: JSON.stringify({
            username: this.newUserUsername,
            email: this.newUserEmail || null,
          }),
        });
        await this.loadUsers();
        this.userAddOpen = false;
        this.showToast(`User ${this.newUserUsername} added`);
      } catch (error) {
        this.showError(error);
      } finally {
        this.userCreating = false;
      }
    },
    async toggleManagedUser(user) {
      const status = user.status === "active" ? "disabled" : "active";
      try {
        await this.api(`/api/users/${user.id}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status }),
        });
        await this.loadUsers();
        this.showToast(`User ${user.username} ${status}`);
      } catch (error) {
        this.showError(error);
      }
    },
    requestDeleteUser(user) {
      if (user.role !== "admin") this.userDeleteTarget = user;
    },
    async confirmDeleteUser() {
      const user = this.userDeleteTarget;
      if (!user) return;
      try {
        await this.api(`/api/users/${user.id}`, { method: "DELETE" });
        await this.loadUsers();
        this.userDeleteTarget = null;
        this.showToast(`User ${user.username} deleted`);
      } catch (error) {
        this.showError(error);
      }
    },
    async loadChats() {
      try {
        this.chats = (await this.api("/api/chats")).chats;
      } catch (e) {
        this.showError(e);
      }
    },
    startEditingChatTitle() {
      if (this.sharedMode || !this.activeChat) return;
      this.chatTitleDraft = this.activeChat.title || "";
      this.editingChatTitle = true;
      this.$nextTick(() => {
        document.getElementById("chat-title-input")?.focus();
      });
    },
    cancelEditingChatTitle() {
      this.editingChatTitle = false;
      this.chatTitleDraft = "";
    },
    async saveChatTitle() {
      if (!this.editingChatTitle || this.chatTitleSaving) return;
      const chatId = this.activeChat?.id;
      if (!chatId) return;
      const title = this.chatTitleDraft.trim();
      if (!title) {
        this.showError(new Error("Chat title cannot be empty"));
        this.chatTitleDraft = this.activeChat?.title || "";
        return;
      }
      this.chatTitleSaving = true;
      try {
        const updated = await this.api(`/api/chats/${chatId}`, {
          method: "PATCH",
          body: JSON.stringify({ title }),
        });
        if (this.activeChat?.id === chatId) {
          this.activeChat = updated;
          const sidebarChat = this.chats.find((chat) => chat.id === updated.id);
          if (sidebarChat) Object.assign(sidebarChat, updated);
          document.title = `${updated.title} · OMA studio`;
          this.cancelEditingChatTitle();
        }
      } catch (error) {
        this.showError(error);
      } finally {
        this.chatTitleSaving = false;
      }
    },
    openChatSearch() {
      this.chatSearchQuery = "";
      this.chatSearchAgentFilter = "";
      this.chatSearchAgentPickerOpen = false;
      this.searchOpen = true;
    },
    searchChatResults() {
      const query = this.chatSearchQuery.trim().toLowerCase();
      const matches = this.chats.filter((chat) => {
        const matchesAgent =
          !this.chatSearchAgentFilter ||
          chat.agent_id === this.chatSearchAgentFilter;
        const matchesQuery =
          !query ||
          chat.title.toLowerCase().includes(query) ||
          this.agentName(chat.agent_id).toLowerCase().includes(query);
        return matchesAgent && matchesQuery;
      });
      return matches.slice(0, query || this.chatSearchAgentFilter ? 50 : 5);
    },
    selectChatSearchAgent(agentId) {
      this.chatSearchAgentFilter = agentId;
      this.chatSearchAgentPickerOpen = false;
    },
    selectSearchChat(chat) {
      this.searchOpen = false;
      this.openChat(chat);
    },
    async loadHealth() {
      try {
        this.activeProcesses =
          (await this.api("/api/health")).active_processes || 0;
      } catch {}
    },
    async loadResources() {
      try {
        await this.refreshResources();
      } catch (e) {
        this.showError(e);
      }
    },
    async refreshResources() {
      this.resources = await this.api("/api/resources");
      if (this.resources.tools?.length) this.toolCatalog = this.resources.tools;
      return this.resources;
    },
    marketCatalogItems(kind) {
      const items = this.resources[kind] || [];
      const query = this.marketCatalogSearch.trim().toLowerCase();
      if (!query) return items;
      return items.filter((item) =>
        `${item.name || ""} ${item.description || ""}`
          .toLowerCase()
          .includes(query),
      );
    },
    async searchMarketSkills() {
      const query = this.marketSearch.trim();
      if (!query) {
        this.marketSearchResults = [];
        this.marketSearchError = "Enter a skill or topic to search.";
        return;
      }
      this.marketSearchLoading = true;
      this.marketSearchError = "";
      try {
        const githubSource = this.marketSkillGitHubSource(query);
        const data = await this.api(
          githubSource ? "/api/market/skills/preview" : "/api/market/skills/search",
          {
          method: "POST",
            body: JSON.stringify(
              githubSource
                ? { source: githubSource }
                : { query, owner: this.marketOwner.trim() || null },
            ),
          },
        );
        this.marketSearchResults = data.results || [];
      } catch (error) {
        this.marketSearchResults = [];
        this.marketSearchError = error.message;
      } finally {
        this.marketSearchLoading = false;
      }
    },
    marketSkillGitHubSource(value) {
      const source = value.trim().replace(/\/$/, "");
      return /^(?:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+|https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?(?:\/tree\/[^/]+(?:\/.*)?)?|git@github\.com:[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?|ssh:\/\/git@github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(?:\.git)?)$/i.test(source)
        ? source
        : "";
    },
    openMarketInstall() {
      this.marketSearch = "";
      this.marketOwner = "";
      this.marketSearchResults = [];
      this.marketSearchError = "";
      this.marketExtensionPackage = "";
      this.marketInstallOpen = true;
    },
    closeMarketInstall() {
      if (this.marketActionSkill || this.marketExtensionAction) return;
      this.marketInstallOpen = false;
      this.marketSearchError = "";
    },
    marketSkillInstalled(result) {
      return this.resources.skills.some(
        (item) =>
          item.name === result.skill &&
          (!result.repo || item.source === result.repo || !item.source),
      );
    },
    async installMarketSkill(result) {
      this.marketActionSkill = result.skill;
      this.marketSearchError = "";
      try {
        await this.api("/api/market/skills/install", {
          method: "POST",
          body: JSON.stringify({ source: result.repo, skill: result.skill }),
        });
        await this.refreshResources();
        this.marketInstallOpen = false;
        this.marketSearchResults = [];
        this.showToast(`Skill ${result.skill} installed`);
      } catch (error) {
        this.showError(error);
      } finally {
        this.marketActionSkill = "";
      }
    },
    async installMarketExtension() {
      const packageInput = this.marketExtensionPackage.trim();
      if (!packageInput) {
        this.showError(new Error("Enter an npm package id"));
        return;
      }
      this.marketExtensionAction = true;
      try {
        const data = await this.api("/api/market/extensions/install", {
          method: "POST",
          body: JSON.stringify({ package: packageInput }),
        });
        await this.refreshResources();
        const installed = data.package?.replace(/^npm:/, "") || packageInput;
        this.marketInstallOpen = false;
        this.marketExtensionPackage = "";
        this.showToast(`Extension ${installed} installed`);
      } catch (error) {
        this.showError(error);
      } finally {
        this.marketExtensionAction = false;
      }
    },
    marketResourceSource(kind, item) {
      if (item?.source) return item.source;
      if (kind === "extensions" && item?.path?.includes("/npm/node_modules/"))
        return `npm:${item.name}`;
      if (kind === "extensions" && item?.path) return item.path;
      if (kind === "skills" && item?.name) return item.name;
      return "";
    },
    marketResourceAuthor(kind, item) {
      const author = typeof item?.author === "string" ? item.author.trim() : "";
      const sourceAuthor =
        kind === "skills" && item?.source
          ? item.source.split("/", 1)[0].trim()
          : "";
      return (author || sourceAuthor || "admin").slice(0, 10);
    },
    openMarketUninstall(kind, item) {
      if (!this.marketResourceSource(kind, item)) return;
      this.marketUninstallTarget = { kind, item };
    },
    async confirmMarketUninstall() {
      const target = this.marketUninstallTarget;
      if (!target) return;
      const { kind, item } = target;
      const path =
        kind === "extensions"
          ? "/api/market/extensions/uninstall"
          : "/api/market/skills/uninstall";
      const packageSource = this.marketResourceSource(kind, item);
      const payload =
        kind === "extensions"
          ? packageSource.startsWith("npm:")
            ? { package: packageSource }
            : { path: packageSource }
          : {
              source: item.source || null,
              skill: item.name,
            };
      try {
        await this.api(path, {
          method: "POST",
          body: JSON.stringify(payload),
        });
        await this.refreshResources();
        this.marketUninstallTarget = null;
        this.showToast(
          `${kind === "extensions" ? "Extension" : "Skill"} ${item.name} uninstalled`,
        );
      } catch (error) {
        this.showError(error);
      }
    },
    showToast(message, kind = "success") {
      this.error = "";
      this.toastMessage = message;
      this.toastKind = kind;
      setTimeout(() => {
        this.toastMessage = "";
      }, 5000);
    },
    async toggleFiles() {
      this.filesOpen = !this.filesOpen;
      if (this.filesOpen) this.linkDrawerOpen = false;
      if (this.filesOpen && this.activeChat && !this.files.length) {
        if (this.sharedMode) await this.loadSharedFiles();
        else await this.loadChatFiles();
      }
    },
    async loadSharedFiles() {
      this.filesLoading = true;
      try {
        this.files = (
          await this.api(`/api/share/${this.sharedToken}/files`)
        ).files;
      } catch (e) {
        this.showError(e);
      } finally {
        this.filesLoading = false;
      }
    },
    async loadChatFiles() {
      this.filesLoading = true;
      try {
        this.files = (
          await this.api(`/api/chats/${this.activeChat.id}/files`)
        ).files;
      } catch (e) {
        this.showError(e);
      } finally {
        this.filesLoading = false;
      }
    },
    async loadLibrary(page = this.libraryPage) {
      this.libraryLoading = true;
      this.libraryPage = Math.max(1, page);
      try {
        const params = new URLSearchParams({
          page: String(this.libraryPage),
          page_size: "20",
        });
        if (this.librarySearch.trim())
          params.set("search", this.librarySearch.trim());
        if (this.libraryAgentFilter)
          params.set("agent_id", this.libraryAgentFilter);
        const data = await this.api(`/api/library/files?${params}`);
        this.libraryFiles = data.files;
        this.libraryPages = data.pages;
        this.libraryTotal = data.total;
      } catch (e) {
        this.showError(e);
      } finally {
        this.libraryLoading = false;
      }
    },
    selectLibraryAgent(agentId) {
      this.libraryAgentFilter = agentId;
      this.libraryAgentPickerOpen = false;
      this.loadLibrary(1);
    },
    selectAutopilotAgent(agentId) {
      this.autopilotAgentFilter = agentId;
      this.autopilotAgentPickerOpen = false;
      this.loadAutopilots();
    },
    openFile(file) {
      if (!this.activeChat) return;
      const query = this.sharedMode
        ? new URLSearchParams({ share: this.sharedToken, path: file.path, from: "chat" })
        : new URLSearchParams({ chat_id: this.activeChat.id, path: file.path, from: "chat" });
      this.openInternalTab(`/file-view?${query.toString()}`);
    },
    openLibraryFile(file) {
      const query = new URLSearchParams({
        chat_id: file.chat_id,
        path: file.path,
        from: "library",
      });
      this.openInternalTab(`/file-view?${query.toString()}`);
    },
    openLibraryChat(file) {
      this.openInternalTab(`/chat/${encodeURIComponent(file.chat_id)}`);
    },
    openInternalTab(url) {
      if (typeof url !== "string" || !url.startsWith("/")) return;
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.target = "_blank";
      anchor.rel = "noopener";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    },
    leaveFileViewer() {
      const params = new URLSearchParams(location.search);
      if (document.referrer.startsWith(location.origin) && history.length > 1) {
        history.back();
      } else if (params.get("from") === "chat" && params.get("chat_id")) {
        location.assign(`/chat/${encodeURIComponent(params.get("chat_id"))}`);
      } else {
        location.assign("/library");
      }
    },
    downloadUrl(file) {
      return `/api/chats/${encodeURIComponent(file.chat_id)}/files/download?path=${encodeURIComponent(file.path)}`;
    },
    async loadFileViewer() {
      const params = new URLSearchParams(location.search);
      const share = params.get("share");
      const chatId = params.get("chat_id");
      const path = params.get("path");
      if ((!chatId && !share) || !path) {
        this.showError(new Error("File reference is incomplete"));
        return;
      }
      try {
        const data = share
          ? await this.api(
              `/api/share/${encodeURIComponent(share)}/files/content?path=${encodeURIComponent(path)}`,
            )
          : await this.api(
              `/api/chats/${encodeURIComponent(chatId)}/files/content?path=${encodeURIComponent(path)}`,
            );
        this.fileViewer = {
          chatId: chatId || `share:${share}`,
          path,
          content: data.content,
        };
        document.title = path.split("/").pop() || "File";
        setTimeout(() => this.renderMermaidDiagrams(), 0);
      } catch (e) {
        this.showError(e);
      }
    },
    renderMermaidDiagrams() {
      if (!window.mermaid) return;
      try {
        window.mermaid.initialize({
          startOnLoad: false,
          theme: this.theme === "dark" ? "dark" : "default",
        });
        window.mermaid.run({
          nodes: [...document.querySelectorAll(".file-markdown .mermaid")],
        });
      } catch {}
    },
    formatBytes(bytes) {
      if (!Number.isFinite(bytes)) return "";
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    },
    formatDateTime(value) {
      return value
        ? new Date(value).toLocaleString(undefined, {
            year: "numeric",
            month: "numeric",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          })
        : "—";
    },
    resizeStartInput(event) {
      const input = event.target;
      input.style.height = "auto";
      input.style.height = `${Math.min(input.scrollHeight, 320)}px`;
    },
    modeQuery() {
      const value = new URLSearchParams(location.search).get("mode");
      return ["development", "production"].includes(value)
        ? `?mode=${value}`
        : "";
    },
    syncModeFromUrl() {
      const value = new URLSearchParams(location.search).get("mode");
      this.mode = ["development", "production"].includes(value)
        ? value
        : this.resources.mode || "production";
    },
    go(page) {
      this.page = page;
      const path =
        page === "agents"
          ? "/agents"
          : page === "market"
            ? "/market"
          : page === "library"
            ? "/library"
            : page === "autopilots"
              ? "/autopilots"
              : this.activeChat
                ? `/chat/${this.activeChat.id}`
                : "/chat";
      history.pushState({}, "", path + this.modeQuery());
      if (page === "library") this.loadLibrary(1);
      if (page === "autopilots") this.loadAutopilots();
    },
    openCronBuilder() {
      this.syncCronBuilder();
      this.cronBuilderOpen = true;
    },
    syncCronBuilder() {
      const parts = this.autopilotCron.trim().split(/\s+/);
      if (parts.length !== 5) return;
      const [minute, hour, dom, month, dow] = parts;
      this.cronMinute = minute === "*" ? "0" : minute;
      this.cronHour = hour === "*" ? "9" : hour;
      this.cronDay = dow === "*" ? ["1"] : dow.split(",");
      this.cronDayOfMonth = dom === "*" ? "1" : dom;
      this.cronMonth = month === "*" ? "1" : month;
      if (minute !== "*" && hour === "*") this.cronFrequency = "hourly";
      else if (dow !== "*") this.cronFrequency = "weekly";
      else if (dom !== "*" && month === "*") this.cronFrequency = "monthly";
      else if (dom !== "*" && month !== "*") this.cronFrequency = "yearly";
      else this.cronFrequency = "daily";
    },
    setCronFrequency(value) {
      this.cronFrequency = value;
      this.autopilotCron = this.buildCron();
    },
    toggleCronDay(day) {
      this.cronDay = this.cronDay.includes(day)
        ? this.cronDay.length > 1
          ? this.cronDay.filter((item) => item !== day)
          : this.cronDay
        : [...this.cronDay, day];
      this.autopilotCron = this.buildCron();
    },
    cronHours() {
      return Array.from({ length: 24 }, (_, index) => String(index));
    },
    cronDaysOfMonth() {
      return Array.from({ length: 31 }, (_, index) => String(index + 1));
    },
    cronMonths() {
      return Array.from({ length: 12 }, (_, index) => String(index + 1));
    },
    buildCron() {
      const m = this.cronMinute,
        h = this.cronHour;
      if (this.cronFrequency === "hourly") return `${m} * * * *`;
      if (this.cronFrequency === "weekly")
        return `${m} ${h} * * ${this.cronDay
          .slice()
          .sort((a, b) => Number(a) - Number(b))
          .join(",")}`;
      if (this.cronFrequency === "monthly")
        return `${m} ${h} ${this.cronDayOfMonth} * *`;
      if (this.cronFrequency === "yearly")
        return `${m} ${h} ${this.cronDayOfMonth} ${this.cronMonth} *`;
      return `${m} ${h} * * *`;
    },
    applyCronBuilder() {
      this.autopilotCron = this.buildCron();
      this.cronBuilderOpen = false;
    },
    async loadAutopilots() {
      this.autopilotLoading = true;
      try {
        const params = new URLSearchParams();
        if (this.autopilotSearch.trim())
          params.set("search", this.autopilotSearch.trim());
        if (this.autopilotAgentFilter)
          params.set("agent_id", this.autopilotAgentFilter);
        this.autopilots = (
          await this.api(`/api/autopilots?${params}`)
        ).autopilots;
      } catch (e) {
        this.showError(e);
      } finally {
        this.autopilotLoading = false;
      }
    },
    newAutopilot() {
      this.autopilotEditing = null;
      this.autopilotName = "";
      this.autopilotInstruction = "";
      this.autopilotAgentId = this.agents[0]?.id || "";
      this.autopilotCron = "0 * * * *";
      this.autopilotStartsAt = "";
      this.autopilotEndsAt = "";
      this.autopilotDialog = true;
    },
    editAutopilot(item) {
      this.autopilotEditing = item;
      this.autopilotName = item.name;
      this.autopilotInstruction = item.instruction;
      this.autopilotAgentId = item.agent_id;
      this.autopilotCron = item.cron;
      this.autopilotStartsAt = item.starts_at || "";
      this.autopilotEndsAt = item.ends_at || "";
      this.autopilotDialog = true;
    },
    async saveAutopilot() {
      if (
        !this.autopilotName.trim() ||
        !this.autopilotInstruction.trim() ||
        !this.autopilotAgentId
      )
        return;
      this.autopilotSaving = true;
      try {
        const payload = {
          name: this.autopilotName,
          instruction: this.autopilotInstruction,
          agent_id: this.autopilotAgentId,
          cron: this.autopilotCron,
          starts_at: this.autopilotStartsAt || null,
          ends_at: this.autopilotEndsAt || null,
        };
        const item = this.autopilotEditing
          ? await this.api(`/api/autopilots/${this.autopilotEditing.id}`, {
              method: "PATCH",
              body: JSON.stringify(payload),
            })
          : await this.api("/api/autopilots", {
              method: "POST",
              body: JSON.stringify(payload),
            });
        const index = this.autopilots.findIndex((row) => row.id === item.id);
        if (index >= 0) this.autopilots[index] = item;
        else this.autopilots.unshift(item);
        this.autopilotDialog = false;
      } catch (e) {
        this.showError(e);
      } finally {
        this.autopilotSaving = false;
      }
    },
    async toggleAutopilot(item) {
      try {
        const updated = await this.api(`/api/autopilots/${item.id}`, {
          method: "PATCH",
          body: JSON.stringify({ enabled: !item.enabled }),
        });
        Object.assign(item, updated);
      } catch (e) {
        this.showError(e);
      }
    },
    deleteAutopilot(item) {
      this.autopilotDeleteTarget = item;
    },
    async confirmDeleteAutopilot() {
      const item = this.autopilotDeleteTarget;
      if (!item) return;
      try {
        await this.api(`/api/autopilots/${item.id}`, { method: "DELETE" });
        this.autopilots = this.autopilots.filter((row) => row.id !== item.id);
        this.autopilotDeleteTarget = null;
      } catch (e) {
        this.showError(e);
      }
    },
    async runAutopilot(item) {
      try {
        await this.api(`/api/autopilots/${item.id}/run`, { method: "POST" });
        this.loadAutopilotRuns(item);
      } catch (e) {
        this.showError(e);
      }
    },
    async loadAutopilotRuns(item) {
      this.autopilotRunsOpen = true;
      this.autopilotRuns = [];
      this.autopilotRunsItem = item;
      try {
        this.autopilotRuns = (
          await this.api(`/api/autopilots/${item.id}/runs`)
        ).runs;
      } catch (e) {
        this.showError(e);
      }
    },
    brandClick() {
      if (this.sidebarCollapsed) this.sidebarCollapsed = false;
      else this.newChat();
    },
    toggleMobileSidebar() {
      this.mobileSidebarOpen = !this.mobileSidebarOpen;
    },
    comingSoon(name) {
      this.showError(new Error(`${name} is reserved for the next iteration.`));
    },
    applyThemePreference(value) {
      this.themePreference = ["system", "light", "dark"].includes(value)
        ? value
        : "system";
      const prefersDark = window.matchMedia?.(
        "(prefers-color-scheme: dark)",
      ).matches;
      this.theme =
        this.themePreference === "system"
          ? prefersDark
            ? "dark"
            : "light"
          : this.themePreference;
      document.documentElement.dataset.theme = this.theme;
      localStorage.setItem("oma-theme-preference", this.themePreference);
      localStorage.setItem("pi-theme", this.theme);
    },
    setTheme(_value) {
      this.applyThemePreference(
        localStorage.getItem("oma-theme-preference") || "system",
      );
    },
    toggleTheme() {
      this.applyThemePreference(this.theme === "dark" ? "light" : "dark");
    },
    openSettings() {
      this.settingsTab = "general";
      this.settingsOpen = true;
    },
    saveLanguage() {
      if (this.language !== "en") this.language = "en";
      localStorage.setItem("oma-language", this.language);
    },
    saveTimezone() {
      localStorage.setItem("oma-timezone", this.timezone);
    },
    newChat() {
      this.stopWatching();
      this.resetShare();
      this.cancelEditingChatTitle();
      this.activeChat = null;
      this.messages = [];
      this.files = [];
      this.filesOpen = false;
      this.draft = "";
      this.loading = false;
      this.messagesLoading = false;
      this.error = "";
      this.page = "chat";
      this.agentPickerOpen = false;
      history.pushState({}, "", "/chat" + this.modeQuery());
      if (this.agents.length) this.selectedAgentId = this.agents[0].id;
    },
    async openChat(chat, updateUrl = true) {
      this.stopWatching();
      this.resetShare();
      this.page = "chat";
      this.cancelEditingChatTitle();
      this.activeChat = chat;
      this.files = [];
      this.filesOpen = false;
      if (updateUrl)
        history.pushState({}, "", `/chat/${chat.id}` + this.modeQuery());
      this.messages = [];
      this.messagesLoading = true;
      try {
        const data = await this.api(
          `/api/chats/${chat.id}/messages?mode=${this.mode}`,
        );
        this.messages = this.normalizeMessages(data.messages);
      } catch (e) {
        this.showError(e);
      } finally {
        this.messagesLoading = false;
      }
      if (chat.status === "running" && !this.loading)
        void this.watchChat(chat.id);
    },
    async routeFromUrl() {
      this.syncModeFromUrl();
      if (window.location.pathname === "/file-view") {
        this.page = "file";
        await this.loadFileViewer();
        return;
      }
      if (window.location.pathname === "/library") {
        this.page = "library";
        await this.loadLibrary(1);
        return;
      }
      const match = window.location.pathname.match(/^\/chat\/([^/]+)$/);
      if (window.location.pathname === "/agents") {
        this.page = "agents";
        return;
      }
      this.page = "chat";
      if (match) {
        const chat = this.chats.find(
          (item) => item.id === decodeURIComponent(match[1]),
        );
        if (chat) await this.openChat(chat, false);
        else {
          this.activeChat = null;
          this.messages = [];
          this.showError(new Error("Chat not found"));
        }
      } else {
        this.activeChat = null;
        this.messages = [];
        this.draft = "";
        this.loading = false;
      }
    },
    async sendFirst() {
      if (!this.draft.trim() || !this.selectedAgentId) return;
      try {
        const chat = await this.api("/api/chats", {
          method: "POST",
          body: JSON.stringify({ agent_id: this.selectedAgentId }),
        });
        this.activeChat = chat;
        this.chats.unshift(chat);
        history.pushState({}, "", `/chat/${chat.id}`);
        await this.sendMessage();
        if (this.activeChat?.title === "New conversation") {
          this.chats = this.chats.filter(
            (item) => item.id !== this.activeChat.id,
          );
          this.activeChat = null;
          this.messages = [];
          history.pushState({}, "", "/chat" + this.modeQuery());
        }
      } catch (e) {
        if (this.activeChat?.title === "New conversation")
          this.chats = this.chats.filter(
            (item) => item.id !== this.activeChat.id,
          );
        this.activeChat = null;
        this.messages = [];
        this.showError(e);
      }
    },
    async sendMessage() {
      const content = this.draft.trim();
      if (!content || !this.activeChat || this.loading) return;
      this.draft = "";
      this.messages.push({
        _key: crypto.randomUUID(),
        role: "user",
        content: [{ type: "text", text: content }],
      });
      this.messages.push({
        _key: crypto.randomUUID(),
        role: "assistant",
        content: [{ type: "text", text: "" }],
        _reasoningParts: [{ type: "thinking", thinking: "" }],
        _tools: [],
        _streaming: true,
      });
      this.loading = true;
      const chatId = this.activeChat.id;
      try {
        const requestId = crypto.randomUUID();
        const response = await fetch(`/api/chats/${chatId}/messages`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": requestId,
          },
          body: JSON.stringify({ content }),
        });
        if (!response.ok) {
          const responseId =
            response.headers.get("X-Request-ID") || requestId;
          const contentType = response.headers.get("content-type") || "";
          let data = null;
          if (contentType.includes("json")) {
            try {
              data = await response.json();
            } catch {}
          } else {
            await response.text();
          }
          throw this.errorFromResponse(response, responseId, data);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) break;
          buffer += decoder.decode(chunk.value, { stream: true });
          const frames = buffer.split("\n\n");
          buffer = frames.pop();
          for (const frame of frames) {
            const line = frame
              .split("\n")
              .find((value) => value.startsWith("data: "));
            if (!line) continue;
            const event = JSON.parse(line.slice(6));
            if (event.type === "complete") {
              this.activeChat = event.chat;
              const i = this.messages.length - 1;
              const normalized = this.normalizeMessages(event.messages || []);
              const hasFinal = normalized.some(
                (message) =>
                  message.role === "assistant" &&
                  this.partsText(message.content),
              );
              if (!hasFinal && event.assistant)
                normalized.push({
                  _key: crypto.randomUUID(),
                  role: "assistant",
                  content: [{ type: "text", text: event.assistant }],
                  _reasoningParts: [],
                  _streaming: false,
                });
              this.messages.splice(i, 1, ...normalized);
              const found = this.chats.find((c) => c.id === this.activeChat.id);
              if (found) Object.assign(found, this.activeChat);
            } else if (event.type === "error") {
              throw new Error(event.error);
            } else {
              this.handleTurnEvent(event);
            }
          }
        }
      } catch (e) {
        this.showError(e);
        this.loading = false;
        if (chatId) void this.watchChat(chatId);
        return;
      } finally {
        this.loading = false;
        this.messages = [...this.messages];
      }
    },
    markStreamingAssistantMessageEnd() {
      const i = this.messages.length - 1;
      const current = this.messages[i];
      if (current?.role === "assistant")
        this.messages[i] = { ...current, _thinkingBoundary: true };
    },
    updateStreamingAssistant(value, append) {
      const i = this.messages.length - 1;
      const current = this.messages[i];
      const text = append ? this.partsText(current.content) + value : value;
      this.messages[i] = {
        ...current,
        content: [{ type: "text", text }],
        _thinkingBoundary: false,
      };
    },
    updateStreamingThinking(value) {
      const i = this.messages.length - 1;
      const current = this.messages[i];
      const parts = [...(current._reasoningParts || [])];
      const last = parts[parts.length - 1];
      if (current._thinkingBoundary || !last || last.type !== "thinking")
        parts.push({ type: "thinking", thinking: value });
      else
        parts[parts.length - 1] = {
          ...last,
          thinking: (last.thinking || "") + value,
        };
      this.messages[i] = {
        ...current,
        _reasoningParts: parts,
        _thinkingBoundary: false,
      };
    },
    handleTurnEvent(event) {
      if (event.type === "delta")
        this.updateStreamingAssistant(event.delta, true);
      else if (event.type === "thinking_delta")
        this.updateStreamingThinking(event.delta);
      else if (event.type === "assistant_message_end")
        this.markStreamingAssistantMessageEnd();
      else if (event.type === "final")
        this.updateStreamingAssistant(event.text, false);
      else if (event.type === "tool") {
        const i = this.messages.length - 1;
        this.messages[i] = {
          ...this.messages[i],
          _tools: [...(this.messages[i]._tools || []), event],
        };
      }
    },
    async watchChat(chatId) {
      if (!chatId || this.watchingChat === chatId) return;
      this.watchingChat = chatId;
      try {
        const chat = await this.api(`/api/chats/${chatId}`);
        if (this.activeChat?.id === chatId) this.activeChat = chat;
        const data = await this.api(
          `/api/chats/${chatId}/messages?mode=${this.mode}`,
        );
        if (this.activeChat?.id !== chatId) {
          this.watchingChat = null;
          return;
        }
        const normalized = this.normalizeMessages(data.messages);
        this.messages = normalized;
        const last = normalized[normalized.length - 1];
        const finishedSnapshot = last?.role === "assistant" && !last._streaming;
        if (chat.status !== "running" || finishedSnapshot) {
          this.watchingChat = null;
          this.loading = false;
          return;
        }
        if (!last || last.role !== "assistant" || !last._streaming)
          this.messages.push({
            _key: crypto.randomUUID(),
            role: "assistant",
            content: [{ type: "text", text: "" }],
            _reasoningParts: [{ type: "thinking", thinking: "" }],
            _tools: [],
            _streaming: true,
          });
        const source = new EventSource(`/api/chats/${chatId}/stream`);
        this.streamSource = source;
        source.onmessage = (m) => {
          let event;
          try {
            event = JSON.parse(m.data);
          } catch {
            return;
          }
          if (event.type === "complete" || event.type === "error") {
            source.close();
            this.streamSource = null;
            this.watchingChat = null;
            this.loading = false;
            if (event.type === "error") this.showError(new Error(event.error));
            void this.finishWatch(chatId);
            return;
          }
          if (this.activeChat?.id === chatId) this.handleTurnEvent(event);
        };
        source.onerror = () => {
          source.close();
          this.streamSource = null;
          if (this.watchingChat === chatId) {
            this.watchingChat = null;
            this.startPolling(chatId);
          }
        };
      } catch (e) {
        this.watchingChat = null;
        this.showError(e);
      }
    },
    async finishWatch(chatId) {
      if (this.activeChat?.id !== chatId) return;
      try {
        const data = await this.api(
          `/api/chats/${chatId}/messages?mode=${this.mode}`,
        );
        this.setMessagesIfChanged(data.messages);
        const chat = await this.api(`/api/chats/${chatId}`);
        if (this.activeChat?.id === chatId) {
          this.activeChat = chat;
          const found = this.chats.find((c) => c.id === chatId);
          if (found) Object.assign(found, chat);
        }
        this.loading = false;
      } catch (e) {
        this.showError(e);
      }
    },
    startPolling(chatId) {
      this.stopPolling();
      this.pollTimer = setInterval(async () => {
        if (this.activeChat?.id !== chatId) {
          this.stopPolling();
          return;
        }
        try {
          const chat = await this.api(`/api/chats/${chatId}`);
          if (chat.status !== "running") {
            const data = await this.api(
              `/api/chats/${chatId}/messages?mode=${this.mode}`,
            );
            if (this.activeChat?.id === chatId) {
        this.setMessagesIfChanged(data.messages);
              this.activeChat = chat;
              const found = this.chats.find((c) => c.id === chatId);
              if (found) Object.assign(found, chat);
            }
            this.loading = false;
            this.stopPolling();
            return;
          }
          const data = await this.api(
            `/api/chats/${chatId}/messages?mode=${this.mode}`,
          );
          if (this.activeChat?.id === chatId) {
            const normalized = this.setMessagesIfChanged(data.messages);
            const last = normalized[normalized.length - 1];
            if (last?.role === "assistant" && !last._streaming) {
              this.loading = false;
              this.stopPolling();
            }
          }
        } catch {}
      }, 3000);
    },
    stopPolling() {
      if (this.pollTimer) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
    },
    stopWatching() {
      if (this.streamSource) {
        this.streamSource.close();
        this.streamSource = null;
      }
      this.watchingChat = null;
      this.stopPolling();
    },
    setReasoningOpen(input) {
      const key = input.dataset.reasoningKey;
      if (key) this.reasoningOpen[key] = input.checked;
    },
    stableMessageKey(message, index) {
      return (
        message.id ||
        `${message.role || "message"}:${message.timestamp || ""}:${index}`
      );
    },
    messagesFingerprint(messages) {
      return messages
        .map((message) => {
          const parts = (message.content || [])
            .map(
              (part) =>
                `${part.type || ""}:${part.text || part.thinking || part.name || ""}:${JSON.stringify(part.arguments || "")}`,
            )
            .join("\u001f");
          return `${message.role || ""}|${message.stopReason || ""}|${message._streaming ? "1" : "0"}|${JSON.stringify(message._usage || {})}|${parts}`;
        })
        .join("\u001e");
    },
    setMessagesIfChanged(rawMessages) {
      const normalized = this.normalizeMessages(rawMessages);
      if (
        this.messagesFingerprint(normalized) !==
        this.messagesFingerprint(this.messages)
      )
        this.messages = normalized;
      return normalized;
    },
    isActionableAssistant(message) {
      if (this.sharedMode || this.loading) return false;
      if (message.role !== "assistant" || message._streaming) return false;
      if (!this.partsText(message.content).trim()) return false;
      const candidates = this.messages.filter(
        (item) =>
          item.role === "assistant" &&
          !item._streaming &&
          this.partsText(item.content).trim() &&
          this.messageVisible(item),
      );
      return (
        candidates.length > 0 &&
        candidates[candidates.length - 1]._key === message._key
      );
    },
    copyMessage(message) {
      const text = this.partsText(message.content);
      navigator.clipboard?.writeText(text);
      this.copiedKey = message._key;
      setTimeout(() => {
        if (this.copiedKey === message._key) this.copiedKey = "";
      }, 1500);
    },
    feedbackFor(message) {
      return (
        (this.feedback || {})[`${this.activeChat?.id}:${message._key}`] || ""
      );
    },
    rateMessage(message, value) {
      const key = `${this.activeChat?.id}:${message._key}`;
      const feedback = { ...(this.feedback || {}) };
      if (feedback[key] === value) delete feedback[key];
      else feedback[key] = value;
      this.feedback = feedback;
      localStorage.setItem("oma-feedback", JSON.stringify(feedback));
    },
    startShare() {
      if (!this.activeChat || this.sharedMode) return;
      this.shareMode = true;
    },
    async openSharedChat(token) {
      this.sharedToken = token;
      this.sharedMode = true;
      this.page = "chat";
      this.messagesLoading = true;
      try {
        const data = await this.api(`/api/share/${encodeURIComponent(token)}`);
        this.activeChat = {
          ...(data.chat || {}),
          id: `share:${token}`,
          status: "ready",
        };
        this.messages = this.normalizeMessages(data.messages || []);
        document.title = `${this.activeChat.title || "Shared conversation"} · OMA studio`;
      } catch (e) {
        this.activeChat = null;
        this.messages = [];
        this.showError(e);
      } finally {
        this.messagesLoading = false;
      }
    },
    cancelShare() {
      this.shareMode = false;
    },
    openShareDialog() {
      this.shareStep = "confirm";
    },
    closeShareDialog() {
      this.shareStep = null;
      this.copiedShare = false;
    },
    resetShare() {
      this.shareMode = false;
      this.shareStep = null;
      this.shareUrl = "";
      this.copiedShare = false;
    },
    async createShare() {
      if (!this.activeChat || this.creatingShare) return;
      this.creatingShare = true;
      try {
        const data = await this.api(`/api/chats/${this.activeChat.id}/share`, {
          method: "POST",
        });
        this.shareUrl = `${location.origin}/share/${data.token}`;
        this.shareStep = "created";
        try {
          await navigator.clipboard?.writeText(this.shareUrl);
        } catch {}
      } catch (e) {
        this.showError(e);
      } finally {
        this.creatingShare = false;
      }
    },
    copyShareLink() {
      if (!this.shareUrl) return;
      navigator.clipboard?.writeText(this.shareUrl);
      this.copiedShare = true;
      setTimeout(() => {
        this.copiedShare = false;
      }, 1500);
    },
    async abort() {
      if (!this.activeChat) return;
      try {
        await this.api(`/api/chats/${this.activeChat.id}/abort`, {
          method: "POST",
        });
        this.loading = false;
      } catch (e) {
        this.showError(e);
      }
    },
    normalizeMessages(messages) {
      const archived = [];
      const sessionUsage = {
        input: 0,
        output: 0,
        cacheRead: 0,
        cost: 0,
        search: 0,
        fetch: 0,
      };
      let assistantGroup = null;
      const flushAssistant = () => {
        if (assistantGroup) {
          if (
            assistantGroup._reasoningParts.length ||
            assistantGroup.content.length ||
            assistantGroup._streaming
          )
            archived.push(assistantGroup);
          assistantGroup = null;
        }
      };
      for (const [index, message] of messages.entries()) {
        if (message.role === "toolResult" && this.mode !== "development")
          continue;
        if (message.role === "user") {
          flushAssistant();
          archived.push({
            ...message,
            _key: this.stableMessageKey(message, index),
          });
          continue;
        }
        if (message.role === "toolResult") {
          flushAssistant();
          archived.push({
            ...message,
            _key: this.stableMessageKey(message, index),
          });
          continue;
        }
        if (message.role === "assistant") {
          if (!assistantGroup)
            assistantGroup = {
              _key: this.stableMessageKey(message, index),
              role: "assistant",
              content: [],
              _reasoningParts: [],
              _streaming: false,
            };
          const hasToolCall =
            (message.content || []).some((part) => part.type === "toolCall") ||
            message.stopReason === "toolUse";
          const usage = message.usage || {};
          sessionUsage.input += Number(usage.input) || 0;
          sessionUsage.output += Number(usage.output) || 0;
          sessionUsage.cacheRead += Number(usage.cacheRead) || 0;
          sessionUsage.cost += Number(usage.cost?.total) || 0;
          for (const part of message.content || []) {
            if (part.type !== "toolCall") continue;
            if (part.name === "web_search") sessionUsage.search += 1;
            if (part.name === "web_fetch") sessionUsage.fetch += 1;
          }
          const isFinal =
            !hasToolCall &&
            ["stop", "length", "aborted", "error"].includes(
              message.stopReason,
            ) &&
            (message.content || []).some((part) => part.type === "text");
          for (const part of message.content || []) {
            if (part.type === "thinking" || !isFinal || part.type !== "text")
              assistantGroup._reasoningParts.push(part);
            else assistantGroup.content.push(part);
          }
          assistantGroup._streaming =
            assistantGroup._streaming || message._streaming;
          continue;
        }
        flushAssistant();
        archived.push({ ...message, _key: this.stableMessageKey(message, index) });
      }
      flushAssistant();
      this.sessionUsage = sessionUsage;
      return archived;
    },
    renderMessage(message) {
      const role = message.role || "message";
      const parts = message.content || [];
      if (role === "user")
        return this.escape(this.partsText(parts)).replace(/\n/g, "<br>");
      if (role === "toolResult")
        return this.mode === "development"
          ? this.renderToolResult(message)
          : "";
      if (role === "assistant") {
        const text = this.partsText(parts);
        const reasoning = this.renderReasoning(
          message._reasoningParts || [],
          message._key,
        );
        if (message._streaming && !text)
          return (
            reasoning ||
            '<span class="loading loading-dots loading-xs" aria-label="Waiting for response"></span>'
          );
        return (
          reasoning +
          parts
            .map((part) =>
              part.type === "text"
                ? this.renderFinalMarkdown(part)
                : this.renderPart(part),
            )
            .join("")
        );
      }
      const fallback = this.partsText(parts);
      return `<div class="system-message"><span>${this.escape(role)}</span>${fallback ? `<p>${this.escape(fallback).replace(/\n/g, "<br>")}</p>` : ""}</div>`;
    },
    renderReasoningPart(part) {
      if (part.type === "thinking")
        return `<div class="reasoning-text markdown-part">${this.renderMarkdown(part.thinking || "")}</div>`;
      if (part.type === "text")
        return `<div class="reasoning-text markdown-part">${this.renderMarkdown(part.text || "")}</div>`;
      return this.renderPart(part);
    },
    messageVisible(message) {
      if (message.role === "toolResult") return this.mode === "development";
      if (this.mode !== "production" || message.role !== "assistant")
        return true;
      if (message._streaming) return true;
      return [
        ...(message._reasoningParts || []),
        ...(message.content || []),
      ].some(
        (part) =>
          part.type === "text" ||
          part.type === "thinking" ||
          this.productionToolAllowlist.includes(part.name),
      );
    },
    partsText(parts) {
      return parts
        .filter((part) => part.type === "text")
        .map((part) => part.text || "")
        .join("");
    },
    renderPart(part) {
      if (part.type === "text")
        return `<div class="markdown-part">${this.renderMarkdown(part.text || "")}</div>`;
      if (part.type === "thinking") {
        const value = part.thinking || "";
        return `<details class="process-disclosure"><summary><span class="process-label">Thinking</span></summary><div class="process-detail">${this.escape(value).replace(/\n/g, "<br>")}</div></details>`;
      }
      if (part.type === "toolCall") {
        const name = part.name || "unknown";
        const args = this.toolArgs(part);
        if (
          this.mode === "production" &&
          !this.productionToolAllowlist.includes(name)
        )
          return "";
        const process = this.renderProcessToolCall(name, args);
        if (process !== null) return process;
        const compact = `<span class="tool-kicker">Tool call</span><b>${this.escape(name)}</b>`;
        return `<details class="tool-block"><summary><i class="process-chevron" data-lucide="chevron-right" aria-hidden="true"></i>${compact}<span class="tool-id">${this.escape(part.id || "")}</span></summary><pre>${this.escape(JSON.stringify(args, null, 2))}</pre></details>`;
      }
      return `<details class="tool-block"><summary><i class="process-chevron" data-lucide="chevron-right" aria-hidden="true"></i>${this.escape(part.type || "content")}</summary><pre>${this.escape(JSON.stringify(part, null, 2))}</pre></details>`;
    },
    renderFinalMarkdown(part) {
      const invert = this.theme === "dark" ? " prose-invert" : "";
      return `<div class="markdown-part prose${invert} max-w-none">${this.renderMarkdown(part.text || "")}</div>`;
    },
    processLine(label, value) {
      return `<div class="process-line"><span class="process-label">${this.escape(label)}</span><span class="process-preview">${this.escape(String(value).replace(/\s+/g, " ").trim())}</span></div>`;
    },
    processDisclosure(label, value, detail, kind = "", showPreview = false) {
      return `<details class="process-disclosure ${kind ? `${kind}-disclosure` : ""}"><summary><i class="process-chevron" data-lucide="chevron-right" aria-hidden="true"></i><span class="process-label">${this.escape(label)}</span>${showPreview ? `<span class="process-preview">${this.escape(String(value).replace(/\s+/g, " ").trim())}</span>` : ""}</summary><pre class="process-detail-code ${kind ? `${kind}-code` : ""}">${detail}</pre></details>`;
    },
    highlightCode(source, language) {
      try {
        const normalized = this.normalizeCodeLanguage(language);
        if (window.hljs?.getLanguage(normalized))
          return DOMPurify.sanitize(
            window.hljs.highlight(source, { language: normalized }).value,
          );
      } catch {}
      return this.escape(source);
    },
    normalizeCodeLanguage(language) {
      const aliases = {
        js: "javascript",
        jsx: "javascript",
        ts: "typescript",
        tsx: "typescript",
        py: "python",
        yml: "yaml",
        sh: "bash",
        shell: "bash",
        zsh: "bash",
        html: "xml",
        svg: "xml",
        md: "markdown",
        jsonc: "json",
      };
      const value = String(language || "").trim().toLowerCase();
      return aliases[value] || value;
    },
    renderMarkdown(source) {
      try {
        const doc = new DOMParser().parseFromString(
          DOMPurify.sanitize(marked.parse(source)),
          "text/html",
        );
        const root = doc.body;
        root
          .querySelectorAll("table")
          .forEach((el) => (el.className = "table table-zebra"));
        root
          .querySelectorAll("ul")
          .forEach((el) => (el.className = "list-disc pl-6 space-y-1"));
        root
          .querySelectorAll("ol")
          .forEach((el) => (el.className = "list-decimal pl-6 space-y-1"));
        root
          .querySelectorAll("blockquote")
          .forEach(
            (el) =>
              (el.className = "border-l-4 border-primary pl-4 opacity-80"),
          );
        root.querySelectorAll("pre").forEach((el) => {
          const code = el.querySelector("code");
          const languageClass = [...(code?.classList || [])].find((name) =>
            name.startsWith("language-"),
          );
          const language = languageClass?.slice("language-".length) || "";
          if (this.normalizeCodeLanguage(language) === "mermaid") {
            const diagram = doc.createElement("div");
            diagram.className = "mermaid";
            diagram.textContent = code.textContent || "";
            el.replaceWith(diagram);
          } else {
            el.className =
              "bg-base-200 text-base-content rounded-box p-4 w-full overflow-x-auto my-3";
            if (code) {
              const source = code.textContent || "";
              let highlighted = this.highlightCode(source, language);
              if (!language && window.hljs?.highlightAuto) {
                const detected = window.hljs.highlightAuto(source, [
                  "bash",
                  "javascript",
                  "json",
                  "python",
                  "typescript",
                  "yaml",
                ]);
                if (detected.language && detected.relevance >= 2)
                  highlighted = DOMPurify.sanitize(detected.value);
              }
              code.innerHTML = highlighted;
              code.classList.add("hljs");
            }
          }
        });
        return root.innerHTML;
      } catch {
        return this.escape(source).replace(/\n/g, "<br>");
      }
    },
    toolArgs(part) {
      if (part.arguments && typeof part.arguments === "object")
        return part.arguments;
      try {
        return JSON.parse(part.arguments || "{}");
      } catch {
        return { arguments: part.arguments || "" };
      }
    },
    renderToolResult(message) {
      const content = this.partsText(message.content || []);
      const label = message.toolName || "Tool result";
      return `<details class="tool-result"><summary><i class="process-chevron" data-lucide="chevron-right" aria-hidden="true"></i><span class="tool-kicker">Tool result</span><b>${this.escape(label)}</b><span class="tool-id">${this.escape(message.toolCallId || "")}</span></summary><pre>${this.escape(content)}</pre></details>`;
    },
    escape(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    },
    agentName(id) {
      return this.agents.find((a) => a.id === id)?.name || "unknown agent";
    },
    normalizeResourcePath(path) {
      const normalized = String(path || "").replaceAll("\\", "/");
      const marker = "/.pi/agent";
      const index = normalized.indexOf(marker);
      return index >= 0 ? normalized.slice(index) : normalized;
    },
    resourcePath(kind, path) {
      const catalog =
        kind === "extensions"
          ? this.resources.extensions
          : this.resources.skills;
      const normalized = this.normalizeResourcePath(path);
      return (
        catalog.find(
          (item) => this.normalizeResourcePath(item.path) === normalized,
        )?.path || ""
      );
    },
    resourceNames(paths, kind) {
      if (!paths?.length) return "None";
      const catalog =
        kind === "extensions"
          ? this.resources.extensions
          : this.resources.skills;
      return paths
        .map(
          (path) =>
            catalog.find(
              (item) =>
                this.normalizeResourcePath(item.path) ===
                this.normalizeResourcePath(path),
            )?.name || path.split(/[\\/]/).pop(),
        )
        .join(", ");
    },
    providerName(id) {
      return (
        this.resources.providers.find((item) => item.id === id)?.name ||
        id ||
        ""
      );
    },
    modelName(providerId, modelId) {
      return (
        this.modelsFor(providerId).find((item) => item.id === modelId)?.name ||
        modelId ||
        ""
      );
    },
    chooseAgent(id) {
      this.selectedAgentId = id;
      this.agentPickerOpen = false;
    },
    chatCount(id) {
      return this.chats.filter((c) => c.agent_id === id).length;
    },
    initials(name) {
      return name
        .split(/\s+/)
        .map((w) => w[0])
        .join("")
        .slice(0, 2)
        .toUpperCase();
    },
    relativeTime(value) {
      if (!value) return "";
      const diff = Date.now() - Date.parse(value);
      if (diff < 3600000) return `${Math.max(1, Math.floor(diff / 60000))}m`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h`;
      return new Date(value).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
      });
    },
    formatDate(value) {
      return value
        ? new Date(value).toLocaleDateString(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
          })
        : "—";
    },
    defaultResources(kind) {
      const configKey = {
        extensions: "default_extensions",
        skills: "default_skills",
        mcp_servers: "default_mcp_servers",
      }[kind];
      const valueKey = kind === "mcp_servers" ? "id" : "path";
      const configured = this.resources[configKey] || [];
      return configured
        .map((value) =>
          kind === "mcp_servers"
            ? this.resources[kind].find((item) =>
                [item.id, item.name, item.path].includes(value),
              )?.[valueKey]
            : this.resourcePath(kind, value),
        )
        .filter(Boolean);
    },
    newAgent() {
      this.editingAgent = null;
      this.newAgentName = "";
      this.newAgentInstruction = "";
      this.newAgentAvatarFile = null;
      this.newAgentAvatarPreview = "";
      this.newAgentProvider =
        this.resources.default_provider ||
        this.resources.providers[0]?.id ||
        "";
      this.newAgentModel = this.defaultModelFor(this.newAgentProvider);
      this.newAgentThinkingLevel = this.defaultThinkingLevel();
      this.newAgentTools = (this.resources.default_tools || []).filter((name) =>
        this.toolCatalog.some((tool) => tool.name === name),
      );
      this.newAgentExtensions = this.defaultResources("extensions");
      this.newAgentSkills = this.defaultResources("skills");
      this.newAgentMcpServers = this.defaultResources("mcp_servers");
      this.createDialog = true;
    },
    modelsFor(providerId = this.newAgentProvider) {
      return (
        this.resources.providers.find((item) => item.id === providerId)
          ?.models || []
      );
    },
    thinkingLevelsFor() {
      return (
        this.modelsFor().find((item) => item.id === this.newAgentModel)
          ?.thinking_levels || [
          "off",
          "minimal",
          "low",
          "medium",
          "high",
          "xhigh",
          "max",
        ]
      );
    },
    defaultThinkingLevel() {
      const levels = this.thinkingLevelsFor();
      return levels.includes(this.resources.default_thinking_level)
        ? this.resources.default_thinking_level
        : levels.includes("low")
          ? "low"
          : levels[0] || "off";
    },
    defaultModelFor(providerId) {
      const models = this.modelsFor(providerId);
      if (
        providerId === this.resources.default_provider &&
        models.some((item) => item.id === this.resources.default_model)
      )
        return this.resources.default_model;
      return models[0]?.id || "";
    },
    changeAgentProvider() {
      this.newAgentModel = this.defaultModelFor(this.newAgentProvider);
      this.newAgentThinkingLevel = this.defaultThinkingLevel();
    },
    changeAgentModel() {
      if (!this.thinkingLevelsFor().includes(this.newAgentThinkingLevel))
        this.newAgentThinkingLevel = this.defaultThinkingLevel();
    },
    async submitAgent() {
      if (
        !this.newAgentName.trim() ||
        !this.newAgentInstruction.trim() ||
        !this.newAgentProvider ||
        !this.newAgentModel ||
        !this.newAgentThinkingLevel
      )
        return;
      this.creating = true;
      try {
        const editing = Boolean(this.editingAgent);
        const avatarFile = this.newAgentAvatarFile;
        const payload = {
          name: this.newAgentName,
          instruction: this.newAgentInstruction,
          provider: this.newAgentProvider,
          model: this.newAgentModel,
          thinking_level: this.newAgentThinkingLevel,
          tools: this.newAgentTools,
          extensions: this.newAgentExtensions,
          skills: this.newAgentSkills,
          mcp_servers: this.newAgentMcpServers,
        };
        const agent = this.editingAgent
          ? await this.api(`/api/agents/${this.editingAgent.id}`, {
              method: "PATCH",
              body: JSON.stringify(payload),
            })
          : await this.api("/api/agents", {
              method: "POST",
              body: JSON.stringify(payload),
            });
        const savedAgent =
          !editing && avatarFile
            ? await this.uploadAvatarFile(agent.id, avatarFile)
            : agent;
        await this.refreshAgents();
        const refreshedAgent =
          this.agents.find((item) => item.id === savedAgent.id) || savedAgent;
        this.createDialog = false;
        this.dialog = refreshedAgent;
        this.editingAgent = null;
        this.page = "agents";
        this.showToast(editing ? "Agent updated" : "Agent created");
      } catch (e) {
        this.showError(e);
      } finally {
        this.creating = false;
      }
    },
    toggleAgentTool(name) {
      this.newAgentTools = this.newAgentTools.includes(name)
        ? this.newAgentTools.filter((tool) => tool !== name)
        : [...this.newAgentTools, name];
    },
    avatarUrl(agent) {
      if (!agent?.avatar_path || !agent.id) return "";
      return `/api/agents/${encodeURIComponent(agent.id)}/avatar?v=${encodeURIComponent(agent.updated_at || agent.avatar_path)}`;
    },
    async uploadAvatarFile(agentId, file) {
      const requestId = crypto.randomUUID();
      const response = await fetch(
        `/api/agents/${encodeURIComponent(agentId)}/avatar`,
        {
          method: "PUT",
          headers: {
            "Content-Type": file.type,
            "X-Request-ID": requestId,
          },
          body: file,
        },
      );
      const responseId = response.headers.get("X-Request-ID") || requestId;
      const contentType = response.headers.get("content-type") || "";
      let data = null;
      if (contentType.includes("json")) {
        try {
          data = await response.json();
        } catch {}
      } else {
        await response.text();
      }
      if (!response.ok) throw this.errorFromResponse(response, responseId, data);
      return data;
    },
    async uploadAgentAvatar(event) {
      const file = event.target.files?.[0];
      if (!file) return;
      if (!file.type.startsWith("image/")) {
        this.showError(new Error("Avatar must be an image file"));
        event.target.value = "";
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        this.showError(new Error("Avatar must be 5 MB or smaller"));
        event.target.value = "";
        return;
      }
      if (this.newAgentAvatarPreview) URL.revokeObjectURL(this.newAgentAvatarPreview);
      this.newAgentAvatarFile = file;
      this.newAgentAvatarPreview = URL.createObjectURL(file);
      if (!this.editingAgent) return;
      this.creating = true;
      try {
        const updated = await this.uploadAvatarFile(this.editingAgent.id, file);
        Object.assign(this.editingAgent, updated);
        this.dialog = updated;
        this.newAgentAvatarFile = null;
        this.newAgentAvatarPreview = "";
      } catch (error) {
        this.showError(error);
      } finally {
        this.creating = false;
      }
    },
    toggleResource(kind, path) {
      const key =
        kind === "extensions"
          ? "newAgentExtensions"
          : kind === "skills"
            ? "newAgentSkills"
            : "newAgentMcpServers";
      this[key] = this[key].includes(path)
        ? this[key].filter((item) => item !== path)
        : [...this[key], path];
    },
    deleteAgent(agent) {
      if (!agent.protected) this.confirmTarget = agent;
    },
    deleteChat(chat) {
      this.deleteChatTarget = chat;
    },
    async confirmDeleteChat() {
      const chat = this.deleteChatTarget;
      if (!chat) return;
      try {
        await this.api(`/api/chats/${chat.id}`, { method: "DELETE" });
        this.chats = this.chats.filter((item) => item.id !== chat.id);
        this.deleteChatTarget = null;
        if (this.activeChat?.id === chat.id) this.newChat();
      } catch (e) {
        this.showError(e);
      }
    },
    async confirmDelete() {
      const agent = this.confirmTarget;
      if (!agent) return;
      try {
        await this.api(`/api/agents/${agent.id}`, { method: "DELETE" });
        await this.refreshAgents();
        if (this.dialog?.id === agent.id) this.dialog = null;
        this.confirmTarget = null;
        this.showToast(`Agent ${agent.name} deleted`);
      } catch (e) {
        this.showError(e);
      }
    },
    editAgent(agent) {
      this.editingAgent = agent;
      this.newAgentName = agent.name;
      this.newAgentInstruction = agent.instruction;
      this.newAgentAvatarFile = null;
      this.newAgentAvatarPreview = "";
      this.newAgentProvider =
        agent.provider ||
        this.resources.default_provider ||
        this.resources.providers[0]?.id ||
        "";
      this.newAgentModel =
        agent.model || this.defaultModelFor(this.newAgentProvider);
      this.newAgentThinkingLevel =
        agent.thinking_level || this.defaultThinkingLevel();
      this.newAgentTools = [...(agent.tools || [])];
      this.newAgentExtensions = (agent.extensions || [])
        .map((path) => this.resourcePath("extensions", path))
        .filter(Boolean);
      this.newAgentSkills = (agent.skills || [])
        .map((path) => this.resourcePath("skills", path))
        .filter(Boolean);
      this.newAgentMcpServers = [...(agent.mcp_servers || [])];
      this.dialog = null;
      this.createDialog = true;
    },
    async routeFromUrl() {
      this.syncModeFromUrl();
      if (window.location.pathname === "/file-view") {
        this.page = "file";
        await this.loadFileViewer();
        return;
      }
      if (window.location.pathname === "/library") {
        this.page = "library";
        await this.loadLibrary(1);
        return;
      }
      if (window.location.pathname === "/market") {
        this.page = "market";
        return;
      }
      if (window.location.pathname === "/autopilots") {
        this.page = "autopilots";
        await this.loadAutopilots();
        return;
      }
      const shareMatch = window.location.pathname.match(/^\/share\/([^/]+)$/);
      if (shareMatch) {
        await this.openSharedChat(decodeURIComponent(shareMatch[1]));
        return;
      }
      const match = window.location.pathname.match(/^\/chat\/([^/]+)$/);
      if (window.location.pathname === "/agents") {
        this.page = "agents";
        return;
      }
      this.page = "chat";
      if (match) {
        const chat = this.chats.find(
          (item) => item.id === decodeURIComponent(match[1]),
        );
        if (chat) await this.openChat(chat, false);
        else {
          this.activeChat = null;
          this.messages = [];
          this.showError(new Error("Chat not found"));
        }
      } else {
        this.activeChat = null;
        this.messages = [];
        this.draft = "";
        this.loading = false;
      }
    },
    renderWebActivity(name, args) {
      const result = args._webResult || args.webResult;
      if (!result) return null;
      const text = this.partsText(result.content || []);
      const items =
        name === "web_search"
          ? this.parseSearchResults(text)
          : this.parseFetchResult(text, result, args);
      if (!items.length)
        return this.processLine(
          name === "web_search" ? "Search" : "Read",
          name === "web_search" ? args.query || "" : args.url || "",
        );
      return this.renderWebActivityItems(name, items);
    },
    renderWebActivityItems(name, items) {
      window.omaPlatform = this;
      const key = crypto.randomUUID();
      this.webActivities[key] = { kind: name, items };
      const label =
        name === "web_search"
          ? `Search found ${items.length} pages`
          : `Read ${items.length} pages`;
      const viewAll =
        items.length > 5
          ? '<span class="web-activity-more">View all</span>'
          : "";
      const pages =
        name === "web_fetch"
          ? `<span class="web-activity-pages">${items
              .slice(0, 5)
              .map(
                (item) =>
                  `<a href="${this.escape(item.url)}" title="${this.escape(item.title)}" target="_blank" rel="noopener" onclick="event.stopPropagation()"><span class="web-activity-page-title">${this.escape(this.truncateLabel(item.title))}</span><i data-lucide="external-link"></i></a>`,
              )
              .join("")}</span>`
          : "";
      const sites =
        name === "web_search"
          ? `<span class="web-activity-sites">${items
        .slice(0, 5)
        .map((item) =>
          item.favicon
            ? `<img src="${this.escape(item.favicon)}" alt="" loading="lazy" onerror="this.hidden=true">`
            : "",
        )
        .join(
          "",
        )}</span>`
          : "";
      return `<div role="button" tabindex="0" class="web-activity web-activity-${name}" data-web-activity-id="${key}" onclick="event.stopPropagation();window.omaPlatform.openWebActivity(this)" onkeydown="if(event.key === 'Enter' || event.key === ' ') window.omaPlatform.openWebActivity(this)"><span class="web-activity-label">${label}</span>${sites}${pages}${viewAll}<span class="web-activity-arrow"><i data-lucide="chevron-right" aria-hidden="true"></i></span></div>`;
    },
    parseSearchResults(text) {
      const items = [];
      const pattern =
        /(?:^|\n)\s*\d+\.\s+\*\*(.+?)\*\*\s*\n([\s\S]*?)\n(https?:\/\/\S+)/g;
      let match;
      while ((match = pattern.exec(text))) {
        const url = match[3].replace(/[)>.,]+$/, "");
        items.push({
          title: match[1].trim(),
          snippet: match[2].trim(),
          url,
          favicon: this.faviconFor(url),
        });
      }
      return items;
    },
    parseFetchResult(text, result, args) {
      const url = result.details?.sourceUrl || args.url || "";
      if (!url) return [];
      const titleLine = text.match(/^\s*Title:\s*(.+)$/im)?.[1]?.trim();
      const heading = text.match(/^#{1,3}\s+(.+)$/m)?.[1]?.trim();
      let title = titleLine || heading || "";
      if (/^(?:url(?:\s+source)?:\s*)?https?:\/\//i.test(title))
        title = heading || "";
      try {
        title = title || new URL(url).hostname;
      } catch {
        title = title || url;
      }
      return [{ title, url, snippet: "", favicon: this.faviconFor(url) }];
    },
    truncateLabel(value, limit = 20) {
      const characters = [...String(value || "")];
      return characters.length > limit
        ? `${characters.slice(0, limit).join("")}…`
        : characters.join("");
    },
    formatCompactNumber(value) {
      const number = Number(value) || 0;
      if (number >= 1000000) return `${(number / 1000000).toFixed(1)}M`;
      if (number >= 1000) return `${(number / 1000).toFixed(1)}k`;
      return String(Math.round(number));
    },
    sessionUsageMarkup() {
      const usage = this.sessionUsage || {};
      const stat = (icon, label, value) =>
        `<span class="usage-stat" title="${label}"><i data-lucide="${icon}" aria-hidden="true"></i><span>${this.escape(value)}</span></span>`;
      return [
        stat("arrow-up", "Input tokens", this.formatCompactNumber(usage.input)),
        stat("arrow-down", "Output tokens", this.formatCompactNumber(usage.output)),
        stat("zap", "Cached input tokens", this.formatCompactNumber(usage.cacheRead)),
        usage.search || usage.fetch
          ? `<span class="usage-stat usage-tools" title="Web tool calls"><i data-lucide="globe" aria-hidden="true"></i><span>search ${usage.search || 0} · fetch ${usage.fetch || 0}</span></span>`
          : "",
        stat("coins", "Estimated cost", `$${(Number(usage.cost) || 0).toFixed(2)}`),
      ].join("");
    },
    faviconFor(url) {
      try {
        return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(new URL(url).hostname)}&sz=32`;
      } catch {
        return "";
      }
    },
    openWebActivity(button) {
      const activity = this.webActivities[button.dataset.webActivityId];
      if (!activity) return;
      this.linkDrawerTitle =
        activity.kind === "web_search" ? "Search results" : "Read pages";
      this.linkDrawerItems = activity.items || [];
      this.filesOpen = false;
      this.linkDrawerOpen = true;
    },
    closeDrawersOutside(event) {
      if (!this.filesOpen && !this.linkDrawerOpen) return;
      if (
        event.target.closest?.(".files-drawer") ||
        event.target.closest?.(".files-toggle") ||
        event.target.closest?.(".web-activity")
      )
        return;
      this.filesOpen = false;
      this.linkDrawerOpen = false;
    },
    renderReasoning(parts, messageKey) {
      const entries = [];
      for (const part of parts) {
        if (part.type === "toolCall" && part.name === "web_fetch") {
          const args = this.toolArgs(part);
          const result = args._webResult || part.webResult;
          if (result) {
            const fetchItems = this.parseFetchResult(
              this.partsText(result.content || []),
              result,
              args,
            );
            if (fetchItems.length) {
              const previous = entries[entries.length - 1];
              if (previous?.kind === "web_fetch")
                previous.items.push(...fetchItems);
              else entries.push({ kind: "web_fetch", items: fetchItems });
              continue;
            }
          }
        }
        entries.push({ part });
      }
      const items = entries
        .map((entry) => {
          const html = entry.kind
            ? this.renderWebActivityItems(entry.kind, entry.items)
            : this.renderReasoningPart(entry.part);
          const toolName = entry.kind || entry.part?.name;
          return html
            ? {
                html,
                marker:
                  toolName === "web_search"
                    ? "globe"
                    : toolName === "web_fetch"
                      ? "globe"
                      : "dot",
              }
            : null;
        })
        .filter(Boolean);
      const content = items
        .map(
          (item, index) =>
            `<li><hr class="${index === 0 ? "invisible" : ""}" /><div class="timeline-start">${item.html}</div><div class="timeline-middle">${item.marker === "globe" ? `<i data-lucide="globe" aria-hidden="true"></i>` : '<span class="reasoning-dot">•</span>'}</div>${index < items.length - 1 ? "<hr />" : ""}</li>`,
        )
        .join("");
      if (!content) return "";
      const times = parts
        .flatMap((part) => [part._timestamp, part.webResult?.timestamp])
        .map((value) =>
          typeof value === "number" ? value : Date.parse(String(value || "")),
        )
        .filter(Number.isFinite);
      const seconds =
        times.length > 1
          ? Math.max(
              1,
              Math.round((Math.max(...times) - Math.min(...times)) / 1000),
            )
          : null;
      const label = seconds === null ? "Thought" : `Thought for ${seconds}s`;
      const reasoningKey = `${messageKey || "message"}:reasoning`;
      const checked = this.reasoningOpen[reasoningKey] ? " checked" : "";
      return `<div class="collapse reasoning-collapse"><input type="checkbox" data-reasoning-key="${this.escape(reasoningKey)}" onchange="window.omaPlatform.setReasoningOpen(this)"${checked} /><div class="collapse-title process-label"><i data-lucide="sparkle" aria-hidden="true"></i><span>${label}</span><i class="reasoning-chevron" data-lucide="chevron-down" aria-hidden="true"></i></div><div class="collapse-content"><ul class="timeline timeline-compact timeline-snap-icon timeline-vertical reasoning-timeline">${content}</ul></div></div>`;
    },
    renderProcessToolCall(name, args) {
      if (name === "web_search" || name === "web_fetch")
        return this.renderWebActivity(name, args);
      const renderers = {
        read: () => (args.path ? this.processLine("Read", args.path) : ""),
        write: () => (args.path ? this.processLine("Write", args.path) : ""),
        ls: () => (args.path ? this.processLine("List", args.path) : ""),
        find: () =>
          args.pattern && args.path
            ? this.processLine("Find", `${args.pattern} in ${args.path}`)
            : "",
        grep: () =>
          args.pattern && args.path
            ? this.processLine("Grep", `${args.pattern} in ${args.path}`)
            : "",
        edit: () => (args.path ? this.processLine("Edit", args.path) : ""),
        mcp: () => (args.tool ? this.processLine("Use", args.tool) : ""),
        bash: () =>
          args.command
            ? this.processDisclosure(
                "Run",
                args.command,
                this.highlightCode(args.command, "bash"),
                "bash",
                false,
              )
            : "",
        mcpScript: () =>
          args.code
            ? this.processDisclosure(
                "Run script",
                args.code,
                this.highlightCode(args.code, "javascript"),
                "script",
                false,
              )
            : "",
        project_report: () => "",
      };
      const renderer = renderers[name];
      return renderer ? renderer() : null;
    },
    productionToolAllowlist: [
      "read",
      "write",
      "edit",
      "web_search",
      "web_fetch",
    ],
    showError(error) {
      this.toastMessage = "";
      this.error = error.message || String(error);
      this.runError = this.error;
      const current = this.messages[this.messages.length - 1];
      if (current?.role === "assistant") {
        current._streaming = false;
        current.content = [];
      }
      setTimeout(() => {
        this.error = "";
        this.runError = "";
      }, 5000);
    },
  };
}

// Exposed for the Alpine x-data binding in index.html.
window.platform = platform;
