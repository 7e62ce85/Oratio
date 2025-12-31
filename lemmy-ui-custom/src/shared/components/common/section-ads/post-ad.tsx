import { Component } from "inferno";
import { AdBanner } from "../ad-banner";

interface PostAdProps {
  className?: string;
  customContent?: string;
  postTitle?: string;
  postType?: string;
}

export class PostAd extends Component<PostAdProps, any> {
  render() {
    const { className = "", customContent, postTitle, postType } = this.props;
    
    // Post-specific ad content if no custom content provided
    let adContent = customContent;
    if (!adContent && postType) {
      const typeEmoji = postType === "image" ? "🖼️" : postType === "video" ? "🎥" : postType === "link" ? "🔗" : "📝";
      adContent = `
        <div style="background: #ffffff; padding: 15px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif; border: 1px solid #e6e6e6;">
          <h3 style="margin: 0 0 10px 0; font-size: 18px;">${typeEmoji} Related Services</h3>
          <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.8;">Useful tools related to this ${postType} content</p>
          <a href="#" target="_blank" rel="noopener" onclick="console.log('Post ${postType} ad clicked')" 
             style="background: #333; color: #fff; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
            View Tools
          </a>
        </div>
      `;
    }
    
    return (
      <AdBanner 
        position="sidebar" 
        size="medium" 
        section="post" 
        className={className}
        customContent={adContent}
      />
    );
  }
}
