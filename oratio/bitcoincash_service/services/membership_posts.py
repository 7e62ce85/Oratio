"""
Membership Posts Service
Queries PostgreSQL directly to fetch posts from membership users
in Lemmy API-compatible format with full sorting and pagination support.
"""

import psycopg2
import psycopg2.extras
import os
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger('membership_posts')

# Sorting map: Lemmy SortType → SQL ORDER BY
SORT_MAP = {
    'Active': 'pa.hot_rank_active DESC, pa.published DESC',
    'Hot': 'pa.hot_rank DESC, pa.published DESC',
    'Scaled': 'pa.scaled_rank DESC, pa.published DESC',
    'Controversial': 'pa.controversy_rank DESC, pa.published DESC',
    'New': 'pa.published DESC',
    'Old': 'pa.published ASC',
    'MostComments': 'pa.comments DESC, pa.published DESC',
    'NewComments': 'pa.newest_comment_time DESC, pa.published DESC',
    'TopDay': 'pa.score DESC, pa.published DESC',
    'TopWeek': 'pa.score DESC, pa.published DESC',
    'TopMonth': 'pa.score DESC, pa.published DESC',
    'TopYear': 'pa.score DESC, pa.published DESC',
    'TopAll': 'pa.score DESC, pa.published DESC',
    'TopHour': 'pa.score DESC, pa.published DESC',
    'TopSixHour': 'pa.score DESC, pa.published DESC',
    'TopTwelveHour': 'pa.score DESC, pa.published DESC',
    'TopThreeMonths': 'pa.score DESC, pa.published DESC',
    'TopSixMonths': 'pa.score DESC, pa.published DESC',
    'TopNineMonths': 'pa.score DESC, pa.published DESC',
}

# Time window for "Top" sorts
TOP_TIME_WINDOWS = {
    'TopHour': "NOW() - INTERVAL '1 hour'",
    'TopSixHour': "NOW() - INTERVAL '6 hours'",
    'TopTwelveHour': "NOW() - INTERVAL '12 hours'",
    'TopDay': "NOW() - INTERVAL '1 day'",
    'TopWeek': "NOW() - INTERVAL '1 week'",
    'TopMonth': "NOW() - INTERVAL '1 month'",
    'TopThreeMonths': "NOW() - INTERVAL '3 months'",
    'TopSixMonths': "NOW() - INTERVAL '6 months'",
    'TopNineMonths': "NOW() - INTERVAL '9 months'",
    'TopYear': "NOW() - INTERVAL '1 year'",
    'TopAll': None,  # No time filter
}


def get_postgres_connection():
    """Get a PostgreSQL connection using environment variables."""
    return psycopg2.connect(
        host=os.environ.get('POSTGRES_HOST', 'postgres'),
        port=int(os.environ.get('POSTGRES_PORT', 5432)),
        user=os.environ.get('POSTGRES_USER', 'lemmy'),
        password=os.environ.get('POSTGRES_PASSWORD', ''),
        database=os.environ.get('POSTGRES_DB', 'lemmy'),
    )


def get_membership_user_ids(conn) -> List[int]:
    """
    Get person IDs of active membership users.
    Joins user_memberships (synced from SQLite) with person table.
    """
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.id
        FROM person p
        JOIN user_memberships um ON p.name = um.user_id
        WHERE um.is_active = TRUE
          AND um.expires_at > EXTRACT(EPOCH FROM NOW())
    """)
    ids = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return ids


def fetch_membership_posts(
    sort: str = 'Active',
    page: int = 1,
    limit: int = 20,
    listing_type: str = 'Local',
) -> Dict[str, Any]:
    """
    Fetch posts from membership users with sorting and pagination.
    Returns data in Lemmy API GetPostsResponse format.
    
    Args:
        sort: SortType string (Active, Hot, New, etc.)
        page: Page number (1-indexed)
        limit: Posts per page (default 20)
        listing_type: ListingType (Local, All) — mostly Local for this use case
    
    Returns:
        Dict matching Lemmy's GetPostsResponse: { posts: [...], next_page: "..." }
    """
    conn = None
    try:
        conn = get_postgres_connection()
        
        # Get membership user IDs
        member_ids = get_membership_user_ids(conn)
        if not member_ids:
            return {"posts": [], "next_page": None}
        
        # Build ORDER BY clause
        order_by = SORT_MAP.get(sort, SORT_MAP['Active'])
        
        # Build time window filter for "Top" sorts
        time_filter = ""
        if sort in TOP_TIME_WINDOWS and TOP_TIME_WINDOWS[sort] is not None:
            time_filter = f"AND p.published > {TOP_TIME_WINDOWS[sort]}"
        
        # Calculate offset
        offset = (page - 1) * limit
        
        # Placeholders for member IDs
        id_placeholders = ','.join(['%s'] * len(member_ids))
        
        # Main query: fetch posts with all related data in Lemmy API format
        query = f"""
            SELECT 
                -- Post fields
                p.id AS post_id,
                p.name AS post_name,
                p.url AS post_url,
                p.body AS post_body,
                p.creator_id,
                p.community_id,
                p.removed AS post_removed,
                p.locked AS post_locked,
                TO_CHAR(p.published AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS post_published,
                CASE WHEN p.updated IS NOT NULL 
                    THEN TO_CHAR(p.updated AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
                    ELSE NULL 
                END AS post_updated,
                p.deleted AS post_deleted,
                p.nsfw AS post_nsfw,
                p.embed_title,
                p.embed_description,
                p.thumbnail_url,
                p.ap_id AS post_ap_id,
                p.local AS post_local,
                p.embed_video_url,
                p.language_id,
                p.featured_community,
                p.featured_local,
                p.url_content_type,
                p.alt_text,
                
                -- Creator (person) fields
                pe.id AS person_id,
                pe.name AS person_name,
                pe.display_name AS person_display_name,
                pe.avatar AS person_avatar,
                pe.banned AS person_banned,
                TO_CHAR(pe.published AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS person_published,
                CASE WHEN pe.updated IS NOT NULL
                    THEN TO_CHAR(pe.updated AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
                    ELSE NULL
                END AS person_updated,
                pe.actor_id AS person_actor_id,
                pe.bio AS person_bio,
                pe.local AS person_local,
                pe.deleted AS person_deleted,
                pe.bot_account AS person_bot_account,
                pe.instance_id AS person_instance_id,
                pe.banner AS person_banner,
                
                -- Community fields
                c.id AS community_id_val,
                c.name AS community_name,
                c.title AS community_title,
                c.description AS community_description,
                c.removed AS community_removed,
                TO_CHAR(c.published AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS community_published,
                CASE WHEN c.updated IS NOT NULL
                    THEN TO_CHAR(c.updated AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
                    ELSE NULL
                END AS community_updated,
                c.deleted AS community_deleted,
                c.nsfw AS community_nsfw,
                c.actor_id AS community_actor_id,
                c.local AS community_local,
                c.icon AS community_icon,
                c.banner AS community_banner,
                c.hidden AS community_hidden,
                c.posting_restricted_to_mods,
                c.instance_id AS community_instance_id,
                c.visibility AS community_visibility,
                
                -- Post aggregates (counts)
                pa.comments,
                pa.score,
                pa.upvotes,
                pa.downvotes,
                TO_CHAR(pa.published AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS counts_published,
                TO_CHAR(pa.newest_comment_time AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"') AS newest_comment_time
                
            FROM post p
            JOIN person pe ON p.creator_id = pe.id
            JOIN community c ON p.community_id = c.id
            JOIN post_aggregates pa ON p.id = pa.post_id
            WHERE p.creator_id IN ({id_placeholders})
              AND p.deleted = false
              AND p.removed = false
              AND c.deleted = false
              AND c.removed = false
              {time_filter}
            ORDER BY {order_by}, p.id DESC
            LIMIT %s OFFSET %s
        """
        
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        params = member_ids + [limit + 1, offset]  # limit+1 to check if next page exists
        cursor.execute(query, params)
        
        rows = cursor.fetchall()
        
        # Determine if there's a next page
        has_next_page = len(rows) > limit
        if has_next_page:
            rows = rows[:limit]  # Trim to actual limit
        
        # Build response in Lemmy API format
        posts = []
        for row in rows:
            post_view = build_post_view(row)
            posts.append(post_view)
        
        # next_page cursor (simple page-based, encoded as string)
        next_page = f"MemberP{page + 1}" if has_next_page else None
        
        cursor.close()
        conn.close()
        
        return {
            "posts": posts,
            "next_page": next_page,
        }
        
    except Exception as e:
        logger.error(f"Error fetching membership posts: {str(e)}")
        if conn:
            conn.close()
        return {"posts": [], "next_page": None}


def build_post_view(row) -> Dict[str, Any]:
    """Build a Lemmy-compatible PostView object from a database row."""
    
    # Handle community_visibility enum → string
    visibility = row['community_visibility']
    if isinstance(visibility, str):
        visibility_str = visibility
    else:
        visibility_str = str(visibility) if visibility else 'Public'
    
    return {
        "post": {
            "id": row['post_id'],
            "name": row['post_name'],
            "url": row['post_url'],
            "body": row['post_body'],
            "creator_id": row['creator_id'],
            "community_id": row['community_id'],
            "removed": row['post_removed'],
            "locked": row['post_locked'],
            "published": row['post_published'],
            "updated": row['post_updated'],
            "deleted": row['post_deleted'],
            "nsfw": row['post_nsfw'],
            "embed_title": row['embed_title'],
            "embed_description": row['embed_description'],
            "thumbnail_url": row['thumbnail_url'],
            "ap_id": row['post_ap_id'],
            "local": row['post_local'],
            "embed_video_url": row['embed_video_url'],
            "language_id": row['language_id'],
            "featured_community": row['featured_community'],
            "featured_local": row['featured_local'],
            "url_content_type": row['url_content_type'],
            "alt_text": row['alt_text'],
        },
        "creator": {
            "id": row['person_id'],
            "name": row['person_name'],
            "display_name": row['person_display_name'],
            "avatar": row['person_avatar'],
            "banned": row['person_banned'],
            "published": row['person_published'],
            "updated": row['person_updated'],
            "actor_id": row['person_actor_id'],
            "bio": row['person_bio'],
            "local": row['person_local'],
            "deleted": row['person_deleted'],
            "bot_account": row['person_bot_account'],
            "instance_id": row['person_instance_id'],
            "banner": row['person_banner'],
        },
        "community": {
            "id": row['community_id_val'],
            "name": row['community_name'],
            "title": row['community_title'],
            "description": row['community_description'],
            "removed": row['community_removed'],
            "published": row['community_published'],
            "updated": row['community_updated'],
            "deleted": row['community_deleted'],
            "nsfw": row['community_nsfw'],
            "actor_id": row['community_actor_id'],
            "local": row['community_local'],
            "icon": row['community_icon'],
            "banner": row['community_banner'],
            "hidden": row['community_hidden'],
            "posting_restricted_to_mods": row['posting_restricted_to_mods'],
            "instance_id": row['community_instance_id'],
            "visibility": visibility_str,
        },
        "creator_banned_from_community": False,
        "banned_from_community": False,
        "creator_is_moderator": False,
        "creator_is_admin": False,
        "counts": {
            "post_id": row['post_id'],
            "comments": row['comments'],
            "score": row['score'],
            "upvotes": row['upvotes'],
            "downvotes": row['downvotes'],
            "published": row['counts_published'],
            "newest_comment_time": row['newest_comment_time'],
        },
        "subscribed": "NotSubscribed",
        "saved": False,
        "read": False,
        "hidden": False,
        "creator_blocked": False,
        "unread_comments": 0,
    }
