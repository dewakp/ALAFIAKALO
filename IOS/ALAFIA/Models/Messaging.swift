import Foundation

// MARK: - Conversation

struct Conversation: Codable, Identifiable {
    let id: Int
    let conversationType: String
    let title: String?
    let description: String?
    let avatarUrl: String?
    let specialty: String?
    let priority: String?
    let isUrgent: Bool
    let isArchived: Bool
    let isMuted: Bool
    let allowReplies: Bool
    let createdBy: Int
    let createdAt: String
    let updatedAt: String
    let lastMessageAt: String?
    let lastMessagePreview: String?
    let members: [ConversationMember]?
    let unreadCount: Int?

    var displayTitle: String {
        title ?? (conversationType == "direct" ? "Direct Message" :
                  conversationType == "clinical" ? "Clinical Channel" :
                  conversationType == "care_team" ? "Care Team" : "Group Chat")
    }

    enum CodingKeys: String, CodingKey {
        case id
        case conversationType = "conversation_type"
        case title, description
        case avatarUrl = "avatar_url"
        case specialty, priority
        case isUrgent = "is_urgent"
        case isArchived = "is_archived"
        case isMuted = "is_muted"
        case allowReplies = "allow_replies"
        case createdBy = "created_by"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case lastMessageAt = "last_message_at"
        case lastMessagePreview = "last_message_preview"
        case members
        case unreadCount = "unread_count"
    }
}

struct ConversationMember: Codable, Identifiable {
    let id: Int
    let conversationId: Int
    let userId: Int
    let role: String
    let nickname: String?
    let isMuted: Bool
    let isPinned: Bool
    let notificationsEnabled: Bool
    let lastReadAt: String?
    let joinedAt: String
    let leftAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case conversationId = "conversation_id"
        case userId = "user_id"
        case role, nickname
        case isMuted = "is_muted"
        case isPinned = "is_pinned"
        case notificationsEnabled = "notifications_enabled"
        case lastReadAt = "last_read_at"
        case joinedAt = "joined_at"
        case leftAt = "left_at"
    }
}

// MARK: - Message

struct ConversationMessage: Codable, Identifiable {
    let id: Int
    let conversationId: Int
    let senderId: Int
    let messageType: String
    let content: String?
    let fileUrl: String?
    let fileName: String?
    let fileSize: Int?
    let fileMimeType: String?
    let replyToId: Int?
    let isClinical: Bool
    let isPriority: Bool
    let isEdited: Bool
    let isDeleted: Bool
    let editedAt: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case conversationId = "conversation_id"
        case senderId = "sender_id"
        case messageType = "message_type"
        case content
        case fileUrl = "file_url"
        case fileName = "file_name"
        case fileSize = "file_size"
        case fileMimeType = "file_mime_type"
        case replyToId = "reply_to_id"
        case isClinical = "is_clinical"
        case isPriority = "is_priority"
        case isEdited = "is_edited"
        case isDeleted = "is_deleted"
        case editedAt = "edited_at"
        case createdAt = "created_at"
    }
}

// MARK: - Community Post

struct CommunityPost: Codable, Identifiable {
    let id: Int
    let authorId: Int
    let content: String
    let visibility: String
    let topic: String?
    let hashtags: String?
    let mentions: String?
    let healthCategory: String?
    let isAnonymous: Bool
    let likeCount: Int
    let replyCount: Int
    let repostCount: Int
    let viewCount: Int
    let isRepost: Bool
    let originalPostId: Int?
    let repostComment: String?
    let isPinned: Bool
    let isEdited: Bool
    let isDeleted: Bool
    let isFlagged: Bool
    let createdAt: String
    let updatedAt: String
    let userLiked: Bool?
    let userReaction: String?

    enum CodingKeys: String, CodingKey {
        case id
        case authorId = "author_id"
        case content, visibility, topic, hashtags, mentions
        case healthCategory = "health_category"
        case isAnonymous = "is_anonymous"
        case likeCount = "like_count"
        case replyCount = "reply_count"
        case repostCount = "repost_count"
        case viewCount = "view_count"
        case isRepost = "is_repost"
        case originalPostId = "original_post_id"
        case repostComment = "repost_comment"
        case isPinned = "is_pinned"
        case isEdited = "is_edited"
        case isDeleted = "is_deleted"
        case isFlagged = "is_flagged"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case userLiked = "user_liked"
        case userReaction = "user_reaction"
    }
}

struct PostReply: Codable, Identifiable {
    let id: Int
    let postId: Int
    let authorId: Int
    let content: String
    let parentReplyId: Int?
    let likeCount: Int
    let isEdited: Bool
    let isDeleted: Bool
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case postId = "post_id"
        case authorId = "author_id"
        case content
        case parentReplyId = "parent_reply_id"
        case likeCount = "like_count"
        case isEdited = "is_edited"
        case isDeleted = "is_deleted"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct UserFollow: Codable, Identifiable {
    let id: Int
    let followerId: Int
    let followingId: Int
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case followerId = "follower_id"
        case followingId = "following_id"
        case createdAt = "created_at"
    }
}

// MARK: - DTOs

struct ConversationCreate: Encodable {
    let conversationType: String
    var title: String? = nil
    var description: String? = nil
    var specialty: String? = nil
    var priority: String? = nil
    var isUrgent: Bool = false
    var memberIds: [Int] = []

    enum CodingKeys: String, CodingKey {
        case conversationType = "conversation_type"
        case title, description, specialty, priority
        case isUrgent = "is_urgent"
        case memberIds = "member_ids"
    }
}

struct MessageCreate: Encodable {
    var messageType: String = "text"
    var content: String? = nil
    var fileUrl: String? = nil
    var fileName: String? = nil
    var replyToId: Int? = nil
    var isClinical: Bool = false
    var isPriority: Bool = false

    enum CodingKeys: String, CodingKey {
        case messageType = "message_type"
        case content
        case fileUrl = "file_url"
        case fileName = "file_name"
        case replyToId = "reply_to_id"
        case isClinical = "is_clinical"
        case isPriority = "is_priority"
    }
}

struct PostCreate: Encodable {
    let content: String
    var visibility: String = "public"
    var topic: String? = nil
    var hashtags: String? = nil
    var healthCategory: String? = nil
    var isAnonymous: Bool = false

    enum CodingKeys: String, CodingKey {
        case content, visibility, topic, hashtags
        case healthCategory = "health_category"
        case isAnonymous = "is_anonymous"
    }
}

struct ReplyCreate: Encodable {
    let content: String
    var parentReplyId: Int? = nil

    enum CodingKeys: String, CodingKey {
        case content
        case parentReplyId = "parent_reply_id"
    }
}

struct LikeResponse: Codable {
    let id: Int
    let postId: Int
    let userId: Int
    let reaction: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case postId = "post_id"
        case userId = "user_id"
        case reaction
        case createdAt = "created_at"
    }
}

private struct DetailResponse: Decodable { let detail: String }
