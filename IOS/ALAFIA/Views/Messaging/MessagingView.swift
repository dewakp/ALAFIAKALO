import SwiftUI

// MARK: - ViewModel

@Observable
final class MessagingViewModel {
    var conversations: [Conversation] = []
    var posts: [CommunityPost] = []
    var messages: [ConversationMessage] = []
    var replies: [PostReply] = []
    var selectedPost: CommunityPost?
    var isLoading = false
    var convFilter: String = "all"
    var feedTopic: String = ""
    var errorMessage: String?

    // Conversations
    func loadConversations() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let path = convFilter == "all"
                ? "/messaging/conversations"
                : "/messaging/conversations?conversation_type=\(convFilter)"
            conversations = try await APIClient.shared.get(path)
        } catch { errorMessage = error.localizedDescription }
    }

    func createConversation(_ data: ConversationCreate) async -> Conversation? {
        do {
            let conv: Conversation = try await APIClient.shared.post("/messaging/conversations", body: data)
            await loadConversations()
            return conv
        } catch { errorMessage = error.localizedDescription; return nil }
    }

    // Messages
    func loadMessages(convId: Int) async {
        do {
            messages = try await APIClient.shared.get("/messaging/conversations/\(convId)/messages")
        } catch { errorMessage = error.localizedDescription }
    }

    func sendMessage(convId: Int, content: String) async {
        do {
            let body = MessageCreate(content: content)
            let _: ConversationMessage = try await APIClient.shared.post("/messaging/conversations/\(convId)/messages", body: body)
            await loadMessages(convId: convId)
        } catch { errorMessage = error.localizedDescription }
    }

    func markConversationRead(convId: Int) async {
        struct Resp: Decodable { let detail: String }
        do {
            let _: Resp = try await APIClient.shared.post("/messaging/conversations/\(convId)/read", body: EmptyBody())
        } catch {}
    }

    // Feed
    func loadFeed() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let path = feedTopic.isEmpty
                ? "/messaging/feed"
                : "/messaging/feed?topic=\(feedTopic)"
            posts = try await APIClient.shared.get(path)
        } catch { errorMessage = error.localizedDescription }
    }

    func createPost(_ data: PostCreate) async {
        do {
            let _: CommunityPost = try await APIClient.shared.post("/messaging/feed", body: data)
            await loadFeed()
        } catch { errorMessage = error.localizedDescription }
    }

    func loadPostDetail(postId: Int) async -> CommunityPost? {
        do {
            let post: CommunityPost = try await APIClient.shared.get("/messaging/feed/\(postId)")
            return post
        } catch { errorMessage = error.localizedDescription; return nil }
    }

    func loadReplies(postId: Int) async {
        do {
            replies = try await APIClient.shared.get("/messaging/feed/\(postId)/replies")
        } catch { errorMessage = error.localizedDescription }
    }

    func sendReply(postId: Int, content: String) async {
        do {
            let body = ReplyCreate(content: content)
            let _: PostReply = try await APIClient.shared.post("/messaging/feed/\(postId)/replies", body: body)
            await loadReplies(postId: postId)
            await loadFeed()
        } catch { errorMessage = error.localizedDescription }
    }

    func toggleLike(postId: Int, isLiked: Bool) async {
        do {
            if isLiked {
                try await APIClient.shared.delete("/messaging/feed/\(postId)/like")
            } else {
                let _: LikeResponse = try await APIClient.shared.post("/messaging/feed/\(postId)/like?reaction=like", body: EmptyBody())
            }
            await loadFeed()
        } catch { errorMessage = error.localizedDescription }
    }

    func followUser(userId: Int) async {
        do {
            let _: UserFollow = try await APIClient.shared.post("/messaging/follow/\(userId)", body: EmptyBody())
        } catch { errorMessage = error.localizedDescription }
    }

    func unfollowUser(userId: Int) async {
        do {
            try await APIClient.shared.delete("/messaging/follow/\(userId)")
        } catch { errorMessage = error.localizedDescription }
    }
}



// MARK: - Main View

struct MessagingView: View {
    @State private var vm = MessagingViewModel()
    @State private var tab = 0 // 0=hub, 1=conversations, 2=feed
    @State private var selectedConv: Conversation?
    @State private var showChat = false
    @State private var showCreateConv = false
    @State private var showCreatePost = false
    @State private var showPostDetail = false
    @State private var selectedPostId: Int?

    var body: some View {
            VStack(spacing: 0) {
                // Segmented tabs
                Picker("Section", selection: $tab) {
                    Text("Hub").tag(0)
                    Text("Messages").tag(1)
                    Text("Community").tag(2)
                }
                .pickerStyle(.segmented)
                .padding()

                switch tab {
                case 0: hubView
                case 1: conversationsView
                case 2: feedView
                default: EmptyView()
                }
            }
            .navigationTitle("Messaging")
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button { showCreateConv = true } label: {
                            Label("New Conversation", systemImage: "plus.message")
                        }
                        Button { showCreatePost = true } label: {
                            Label("New Post", systemImage: "square.and.pencil")
                        }
                    } label: {
                        Image(systemName: "plus")
                    }
                }
            }
            .sheet(isPresented: $showCreateConv) { CreateConversationSheet(vm: vm, onCreated: onConvCreated) }
            .sheet(isPresented: $showCreatePost) { CreatePostSheet(vm: vm) }
            .sheet(isPresented: $showChat) {
                if let conv = selectedConv {
                    ChatSheet(vm: vm, conversation: conv)
                }
            }
            .sheet(isPresented: $showPostDetail) {
                if let pid = selectedPostId {
                    PostDetailSheet(vm: vm, postId: pid)
                }
            }
    }

    private func onConvCreated(_ conv: Conversation) {
        selectedConv = conv
        showCreateConv = false
        showChat = true
    }

    // MARK: Hub

    private var hubView: some View {
        ScrollView {
            VStack(spacing: 16) {
                HubCard(icon: "message.fill", title: "Direct Messages", desc: "Private 1-on-1 conversations", color: .blue) {
                    vm.convFilter = "direct"; tab = 1
                    Task { await vm.loadConversations() }
                }
                HubCard(icon: "cross.case.fill", title: "Clinical Channels", desc: "Physician, nurse, social worker messaging", color: .green) {
                    vm.convFilter = "clinical"; tab = 1
                    Task { await vm.loadConversations() }
                }
                HubCard(icon: "person.3.fill", title: "Group Chats", desc: "Group and care team channels", color: .purple) {
                    vm.convFilter = "group"; tab = 1
                    Task { await vm.loadConversations() }
                }
                HubCard(icon: "globe", title: "Community Feed", desc: "Public timeline — share & support", color: .orange) {
                    tab = 2
                    Task { await vm.loadFeed() }
                }
            }
            .padding()
        }
    }

    // MARK: Conversations

    private var conversationsView: some View {
        VStack(spacing: 0) {
            // Filter chips
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(["all", "direct", "clinical", "group", "care_team"], id: \.self) { f in
                        Button {
                            vm.convFilter = f
                            Task { await vm.loadConversations() }
                        } label: {
                            Text(f == "care_team" ? "Care Team" : f.capitalized)
                                .font(.caption)
                                .fontWeight(.semibold)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 6)
                                .background(vm.convFilter == f ? Color.accentColor : Color(.systemGray5))
                                .foregroundStyle(vm.convFilter == f ? .white : .primary)
                                .clipShape(Capsule())
                        }
                    }
                }
                .padding(.horizontal)
                .padding(.bottom, 8)
            }

            if vm.isLoading {
                Spacer()
                ProgressView()
                Spacer()
            } else if vm.conversations.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "message")
                        .font(.system(size: 40))
                        .foregroundStyle(.secondary)
                    Text("No conversations yet")
                        .foregroundStyle(.secondary)
                    Button("Start a Conversation") { showCreateConv = true }
                        .buttonStyle(.borderedProminent)
                }
                Spacer()
            } else {
                List(vm.conversations) { conv in
                    ConversationRow(conv: conv)
                        .contentShape(Rectangle())
                        .onTapGesture {
                            selectedConv = conv
                            showChat = true
                        }
                }
                .listStyle(.plain)
            }
        }
        .task { await vm.loadConversations() }
    }

    // MARK: Feed

    private var feedView: some View {
        VStack(spacing: 0) {
            // Topic bar
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(["", "general", "fitness", "nutrition", "mental-health", "medications", "lifestyle"], id: \.self) { t in
                        Button {
                            vm.feedTopic = t
                            Task { await vm.loadFeed() }
                        } label: {
                            Text(t.isEmpty ? "All" : "#\(t)")
                                .font(.caption)
                                .fontWeight(.semibold)
                                .padding(.horizontal, 14)
                                .padding(.vertical, 6)
                                .background(vm.feedTopic == t ? Color.accentColor : Color(.systemGray5))
                                .foregroundStyle(vm.feedTopic == t ? .white : .primary)
                                .clipShape(Capsule())
                        }
                    }
                }
                .padding(.horizontal)
                .padding(.bottom, 8)
            }

            if vm.isLoading {
                Spacer()
                ProgressView()
                Spacer()
            } else if vm.posts.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "globe")
                        .font(.system(size: 40))
                        .foregroundStyle(.secondary)
                    Text("No posts yet")
                        .foregroundStyle(.secondary)
                    Button("Create Post") { showCreatePost = true }
                        .buttonStyle(.borderedProminent)
                }
                Spacer()
            } else {
                List(vm.posts) { post in
                    PostRow(post: post, onLike: {
                        Task { await vm.toggleLike(postId: post.id, isLiked: post.userLiked ?? false) }
                    })
                    .contentShape(Rectangle())
                    .onTapGesture {
                        selectedPostId = post.id
                        showPostDetail = true
                    }
                }
                .listStyle(.plain)
            }
        }
        .task { await vm.loadFeed() }
    }
}

// MARK: - Hub Card

private struct HubCard: View {
    let icon: String
    let title: String
    let desc: String
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: icon)
                    .font(.title2)
                    .foregroundStyle(color)
                    .frame(width: 40, height: 40)
                    .background(color.opacity(0.12))
                    .clipShape(Circle())
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(.headline)
                    Text(desc).font(.caption).foregroundStyle(.secondary)
                }
                Spacer()
                Image(systemName: "chevron.right")
                    .foregroundStyle(.tertiary)
            }
            .padding()
            .background(Color(.systemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .shadow(color: .black.opacity(0.06), radius: 4, y: 2)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Conversation Row

private struct ConversationRow: View {
    let conv: Conversation

    private var typeColor: Color {
        switch conv.conversationType {
        case "direct": return .blue
        case "clinical": return .green
        case "group": return .purple
        case "care_team": return .orange
        default: return .gray
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(typeColor.opacity(0.15))
                .frame(width: 40, height: 40)
                .overlay {
                    Text(String(conv.displayTitle.prefix(1)))
                        .font(.headline)
                        .foregroundStyle(typeColor)
                }
            VStack(alignment: .leading, spacing: 2) {
                HStack {
                    Text(conv.displayTitle)
                        .font(.subheadline).fontWeight(.semibold)
                        .lineLimit(1)
                    if conv.isUrgent {
                        Text("⚡")
                    }
                }
                Text(conv.lastMessagePreview ?? "No messages yet")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: 4) {
                if let unread = conv.unreadCount, unread > 0 {
                    Text("\(unread)")
                        .font(.caption2).fontWeight(.bold)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 2)
                        .background(Color.accentColor)
                        .clipShape(Capsule())
                }
                if let ts = conv.lastMessageAt {
                    Text(formatShortDate(ts))
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Post Row

private struct PostRow: View {
    let post: CommunityPost
    let onLike: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Author
            HStack(spacing: 8) {
                Circle().fill(Color.blue.opacity(0.15)).frame(width: 30, height: 30)
                    .overlay {
                        Text(post.isAnonymous ? "?" : "#\(post.authorId)")
                            .font(.caption2).fontWeight(.bold)
                            .foregroundStyle(.blue)
                    }
                VStack(alignment: .leading) {
                    Text(post.isAnonymous ? "Anonymous" : "User #\(post.authorId)")
                        .font(.caption).fontWeight(.semibold)
                    Text(formatShortDate(post.createdAt))
                        .font(.caption2).foregroundStyle(.secondary)
                }
                Spacer()
                if post.isPinned { Image(systemName: "pin.fill").font(.caption2).foregroundStyle(.orange) }
                if let topic = post.topic {
                    Text("#\(topic)")
                        .font(.caption2).foregroundStyle(Color.accentColor)
                }
            }

            // Content
            Text(post.content.prefix(300) + (post.content.count > 300 ? "…" : ""))
                .font(.subheadline)
                .lineLimit(5)

            // Health badge
            if let cat = post.healthCategory {
                Text(cat.replacingOccurrences(of: "_", with: " "))
                    .font(.caption2).fontWeight(.semibold)
                    .foregroundStyle(.green)
                    .padding(.horizontal, 10).padding(.vertical, 2)
                    .background(Color.green.opacity(0.1))
                    .clipShape(Capsule())
            }

            // Engagement
            HStack(spacing: 16) {
                Button(action: onLike) {
                    Label("\(post.likeCount)", systemImage: post.userLiked ?? false ? "heart.fill" : "heart")
                        .font(.caption)
                        .foregroundStyle(post.userLiked ?? false ? .red : .secondary)
                }
                .buttonStyle(.plain)

                Label("\(post.replyCount)", systemImage: "bubble.left")
                    .font(.caption).foregroundStyle(.secondary)
                Label("\(post.viewCount)", systemImage: "eye")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Chat Sheet

private struct ChatSheet: View {
    let vm: MessagingViewModel
    let conversation: Conversation
    @State private var msgs: [ConversationMessage] = []
    @State private var text = ""
    @State private var loading = true
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Info bar
                HStack {
                    VStack(alignment: .leading) {
                        Text(conversation.displayTitle).font(.headline)
                        Text("\(conversation.members?.count ?? 0) members · \(conversation.conversationType.replacingOccurrences(of: "_", with: " ").capitalized)")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if conversation.isUrgent {
                        Text("URGENT").font(.caption2).fontWeight(.bold)
                            .foregroundStyle(.white)
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(.red).clipShape(Capsule())
                    }
                }
                .padding(.horizontal).padding(.bottom, 8)

                Divider()

                // Messages
                if loading {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else {
                    ScrollViewReader { proxy in
                        ScrollView {
                            LazyVStack(spacing: 4) {
                                ForEach(msgs) { msg in
                                    MessageBubble(msg: msg, isOwn: msg.senderId == (conversation.createdBy))
                                        .id(msg.id)
                                }
                            }
                            .padding()
                        }
                        .onChange(of: msgs.count) {
                            if let last = msgs.last {
                                proxy.scrollTo(last.id, anchor: .bottom)
                            }
                        }
                    }
                }

                Divider()

                // Input
                HStack(spacing: 8) {
                    TextField("Type a message...", text: $text)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { sendMsg() }
                    Button(action: sendMsg) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.title2)
                            .foregroundStyle(text.isEmpty ? Color.secondary : Color.accentColor)
                    }
                    .disabled(text.isEmpty)
                }
                .padding(12)
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close") { dismiss() }
                }
            }
            .task {
                msgs = []
                loading = true
                await vm.loadMessages(convId: conversation.id)
                msgs = vm.messages
                loading = false
                await vm.markConversationRead(convId: conversation.id)
            }
        }
    }

    private func sendMsg() {
        guard !text.isEmpty else { return }
        let content = text
        text = ""
        Task {
            await vm.sendMessage(convId: conversation.id, content: content)
            msgs = vm.messages
        }
    }
}

// MARK: - Message Bubble

private struct MessageBubble: View {
    let msg: ConversationMessage
    let isOwn: Bool

    var body: some View {
        if msg.isDeleted {
            Text("Message deleted").font(.caption).foregroundStyle(.secondary).italic()
                .frame(maxWidth: .infinity)
        } else if msg.messageType == "system" {
            Text(msg.content ?? "").font(.caption).foregroundStyle(.secondary).italic()
                .frame(maxWidth: .infinity)
        } else {
            HStack {
                if isOwn { Spacer(minLength: 60) }
                VStack(alignment: isOwn ? .trailing : .leading, spacing: 2) {
                    if !isOwn {
                        Text("User #\(msg.senderId)")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                    Text(msg.content ?? "")
                        .font(.subheadline)
                        .padding(.horizontal, 14).padding(.vertical, 8)
                        .background(isOwn ? Color.accentColor : Color(.systemGray5))
                        .foregroundStyle(isOwn ? .white : .primary)
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                    HStack(spacing: 4) {
                        Text(formatTime(msg.createdAt)).font(.caption2).foregroundStyle(.tertiary)
                        if msg.isEdited { Text("(edited)").font(.caption2).foregroundStyle(.tertiary) }
                        if msg.isClinical { Text("🏥").font(.caption2) }
                        if msg.isPriority { Text("⚡").font(.caption2) }
                    }
                }
                if !isOwn { Spacer(minLength: 60) }
            }
        }
    }
}

// MARK: - Create Conversation Sheet

private struct CreateConversationSheet: View {
    let vm: MessagingViewModel
    let onCreated: (Conversation) -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var convType = "direct"
    @State private var title = ""
    @State private var description = ""
    @State private var memberIds = ""
    @State private var specialty = ""
    @State private var priority = "routine"
    @State private var isUrgent = false
    @State private var submitting = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Type") {
                    Picker("Type", selection: $convType) {
                        Text("Direct Message").tag("direct")
                        Text("Clinical").tag("clinical")
                        Text("Group Chat").tag("group")
                        Text("Care Team").tag("care_team")
                    }
                }
                Section("Details") {
                    TextField("Title", text: $title)
                    TextField("Member IDs (comma-separated)", text: $memberIds)
                    TextField("Description", text: $description)
                }
                if convType == "clinical" || convType == "care_team" {
                    Section("Clinical") {
                        TextField("Specialty", text: $specialty)
                        Picker("Priority", selection: $priority) {
                            Text("Routine").tag("routine")
                            Text("Urgent").tag("urgent")
                            Text("Stat").tag("stat")
                        }
                        Toggle("Mark as Urgent", isOn: $isUrgent)
                    }
                }
                Section {
                    Button(submitting ? "Creating..." : "Create Conversation") {
                        submit()
                    }
                    .disabled(submitting || memberIds.isEmpty)
                }
            }
            .navigationTitle("New Conversation")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private func submit() {
        submitting = true
        let ids = memberIds.split(separator: ",").compactMap { Int($0.trimmingCharacters(in: .whitespaces)) }
        var data = ConversationCreate(conversationType: convType, memberIds: ids)
        if !title.isEmpty { data.title = title }
        if !description.isEmpty { data.description = description }
        if !specialty.isEmpty { data.specialty = specialty }
        data.priority = priority
        data.isUrgent = isUrgent
        Task {
            if let conv = await vm.createConversation(data) {
                onCreated(conv)
            }
            submitting = false
        }
    }
}

// MARK: - Create Post Sheet

private struct CreatePostSheet: View {
    let vm: MessagingViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var content = ""
    @State private var visibility = "public"
    @State private var topic = ""
    @State private var hashtags = ""
    @State private var healthCategory = ""
    @State private var isAnonymous = false
    @State private var submitting = false

    private let categories = ["", "fitness", "nutrition", "mood", "mental_health", "medications", "labs", "lifestyle", "general"]
    private let topics = ["", "general", "fitness", "nutrition", "mental-health", "medications", "lifestyle", "community"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Content") {
                    TextEditor(text: $content)
                        .frame(minHeight: 100)
                    Text("\(content.count)/5000").font(.caption2).foregroundStyle(.secondary)
                }
                Section("Settings") {
                    Picker("Visibility", selection: $visibility) {
                        Text("🌍 Public").tag("public")
                        Text("👥 Followers").tag("followers")
                        Text("🤝 Connections").tag("connections")
                        Text("🔒 Private").tag("private")
                    }
                    Picker("Topic", selection: $topic) {
                        Text("— None —").tag("")
                        ForEach(topics.filter { !$0.isEmpty }, id: \.self) { t in
                            Text(t).tag(t)
                        }
                    }
                    Picker("Health Category", selection: $healthCategory) {
                        Text("— None —").tag("")
                        ForEach(categories.filter { !$0.isEmpty }, id: \.self) { c in
                            Text(c.replacingOccurrences(of: "_", with: " ").capitalized).tag(c)
                        }
                    }
                    TextField("Hashtags (comma-separated)", text: $hashtags)
                    Toggle("Post Anonymously", isOn: $isAnonymous)
                }
                Section {
                    Button(submitting ? "Publishing..." : "Publish") {
                        submitting = true
                        var data = PostCreate(content: content, visibility: visibility, isAnonymous: isAnonymous)
                        if !topic.isEmpty { data.topic = topic }
                        if !hashtags.isEmpty { data.hashtags = hashtags }
                        if !healthCategory.isEmpty { data.healthCategory = healthCategory }
                        Task {
                            await vm.createPost(data)
                            submitting = false
                            dismiss()
                        }
                    }
                    .disabled(submitting || content.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
            .navigationTitle("Create Post")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }
}

// MARK: - Post Detail Sheet

private struct PostDetailSheet: View {
    let vm: MessagingViewModel
    let postId: Int
    @State private var post: CommunityPost?
    @State private var replies: [PostReply] = []
    @State private var replyText = ""
    @State private var loading = true
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack {
                if loading {
                    Spacer()
                    ProgressView()
                    Spacer()
                } else if let p = post {
                    ScrollView {
                        VStack(alignment: .leading, spacing: 12) {
                            // Author header
                            HStack(spacing: 8) {
                                Circle().fill(Color.blue.opacity(0.15)).frame(width: 36, height: 36)
                                    .overlay {
                                        Text(p.isAnonymous ? "?" : "#\(p.authorId)")
                                            .font(.caption2).fontWeight(.bold).foregroundStyle(.blue)
                                    }
                                VStack(alignment: .leading) {
                                    Text(p.isAnonymous ? "Anonymous" : "User #\(p.authorId)")
                                        .font(.subheadline).fontWeight(.semibold)
                                    HStack(spacing: 4) {
                                        Text(formatShortDate(p.createdAt)).font(.caption2).foregroundStyle(.secondary)
                                        if let t = p.topic {
                                            Text("#\(t)").font(.caption2).foregroundStyle(Color.accentColor)
                                        }
                                        if p.isEdited { Text("(edited)").font(.caption2).foregroundStyle(.secondary) }
                                    }
                                }
                            }

                            Text(p.content).font(.body)

                            if let cat = p.healthCategory {
                                Text(cat.replacingOccurrences(of: "_", with: " "))
                                    .font(.caption2).fontWeight(.semibold)
                                    .foregroundStyle(.green)
                                    .padding(.horizontal, 10).padding(.vertical, 2)
                                    .background(Color.green.opacity(0.1))
                                    .clipShape(Capsule())
                            }

                            if let tags = p.hashtags {
                                Text(tags.split(separator: ",").map { "#\($0.trimmingCharacters(in: .whitespaces))" }.joined(separator: " "))
                                    .font(.caption).foregroundStyle(Color.accentColor)
                            }

                            // Engagement
                            Divider()
                            HStack(spacing: 20) {
                                Button {
                                    Task { await vm.toggleLike(postId: p.id, isLiked: p.userLiked ?? false) }
                                    Task { post = await vm.loadPostDetail(postId: postId) }
                                } label: {
                                    Label("\(p.likeCount)", systemImage: p.userLiked ?? false ? "heart.fill" : "heart")
                                        .foregroundStyle(p.userLiked ?? false ? .red : .secondary)
                                }
                                Label("\(p.replyCount)", systemImage: "bubble.left")
                                    .foregroundStyle(.secondary)
                                Label("\(p.viewCount)", systemImage: "eye")
                                    .foregroundStyle(.secondary)
                            }
                            .font(.subheadline)
                            Divider()

                            // Reply input
                            HStack(spacing: 8) {
                                TextField("Write a reply...", text: $replyText)
                                    .textFieldStyle(.roundedBorder)
                                    .onSubmit { sendReply() }
                                Button(action: sendReply) {
                                    Image(systemName: "arrow.up.circle.fill")
                                        .font(.title3)
                                        .foregroundStyle(replyText.isEmpty ? Color.secondary : Color.accentColor)
                                }
                                .disabled(replyText.isEmpty)
                            }

                            // Replies
                            Text("Replies (\(replies.count))").font(.headline)
                            if replies.isEmpty {
                                Text("No replies yet. Be the first!")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                            ForEach(replies) { r in
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack(spacing: 6) {
                                        Circle().fill(Color.purple.opacity(0.15)).frame(width: 24, height: 24)
                                            .overlay {
                                                Text("#\(r.authorId)")
                                                    .font(.system(size: 8)).fontWeight(.bold).foregroundStyle(.purple)
                                            }
                                        Text("User #\(r.authorId)").font(.caption).fontWeight(.semibold)
                                        Text(formatShortDate(r.createdAt)).font(.caption2).foregroundStyle(.secondary)
                                        if r.isEdited { Text("(edited)").font(.caption2).foregroundStyle(.secondary) }
                                    }
                                    Text(r.content).font(.subheadline)
                                }
                                .padding(10)
                                .background(Color(.systemGray6))
                                .clipShape(RoundedRectangle(cornerRadius: 10))
                            }
                        }
                        .padding()
                    }
                } else {
                    Text("Post not found").foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Post")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Close") { dismiss() }
                }
            }
            .task {
                loading = true
                post = await vm.loadPostDetail(postId: postId)
                await vm.loadReplies(postId: postId)
                replies = vm.replies
                loading = false
            }
        }
    }

    private func sendReply() {
        guard !replyText.isEmpty else { return }
        let content = replyText
        replyText = ""
        Task {
            await vm.sendReply(postId: postId, content: content)
            replies = vm.replies
            post = await vm.loadPostDetail(postId: postId)
        }
    }
}

// MARK: - Date Helpers

private func formatShortDate(_ iso: String) -> String {
    let clean = iso.replacingOccurrences(of: "\\.\\d+", with: "", options: .regularExpression)
        .replacingOccurrences(of: "+00:00", with: "Z")
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    if let d = f.date(from: clean) {
        let df = DateFormatter()
        df.dateStyle = .short
        df.timeStyle = .short
        return df.string(from: d)
    }
    return String(iso.prefix(16))
}

private func formatTime(_ iso: String) -> String {
    let clean = iso.replacingOccurrences(of: "\\.\\d+", with: "", options: .regularExpression)
        .replacingOccurrences(of: "+00:00", with: "Z")
    let f = ISO8601DateFormatter()
    f.formatOptions = [.withInternetDateTime]
    if let d = f.date(from: clean) {
        let df = DateFormatter()
        df.timeStyle = .short
        return df.string(from: d)
    }
    return String(iso.prefix(5))
}
