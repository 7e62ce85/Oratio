import { Component } from "inferno";
import { AdBanner } from "../ad-banner";

interface CommentsAdProps {
  className?: string;
  customContent?: string;
  commentCount?: number;
}

export class CommentsAd extends Component<CommentsAdProps, any> {
  render() {
    const { className = "", customContent, commentCount } = this.props;
    
    // Comments-specific ad content if no custom content provided
    let adContent = customContent;
    if (!adContent) {
      const encouragementText = commentCount && commentCount > 10 
        ? "활발한 토론에 참여해보세요!" 
        : "첫 번째 댓글을 남겨보세요!";
        
      adContent = `
        <div style="background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); padding: 12px; border-radius: 8px; text-align: center; color: #333; font-family: Arial, sans-serif;">
          <h3 style="margin: 0 0 8px 0; font-size: 16px;">💬 토론 참여</h3>
          <p style="margin: 0 0 12px 0; font-size: 13px; opacity: 0.8;">${encouragementText}</p>
          <a href="#" target="_blank" rel="noopener" onclick="console.log('Comments ad clicked, comment count: ${commentCount || 0}')" 
             style="background: #333; color: #fff; padding: 6px 16px; border-radius: 4px; text-decoration: none; font-weight: bold; display: inline-block; font-size: 12px;">
            참여하기
          </a>
        </div>
      `;
    }
    
    return (
      <AdBanner 
        position="comment" 
        size="medium" 
        section="comments" 
        className={className}
        customContent={adContent}
      />
    );
  }
}
