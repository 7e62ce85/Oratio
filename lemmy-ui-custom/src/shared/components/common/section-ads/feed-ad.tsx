import { Component } from "inferno";
import { AdBanner } from "../ad-banner";

interface FeedAdProps {
  className?: string;
  customContent?: string;
  feedType?: "All" | "Local" | "Subscribed";
}

export class FeedAd extends Component<FeedAdProps, any> {
  render() {
    const { className = "", customContent, feedType } = this.props;
    
    // Feed-specific ad content if no custom content provided
    let adContent = customContent;
    if (!adContent && feedType) {
      const feedEmoji = feedType === "All" ? "🌍" : feedType === "Local" ? "🏠" : "📋";
      const feedName = feedType === "All" ? "전체" : feedType === "Local" ? "로컬" : "구독";
      
      adContent = `
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
          <h3 style="margin: 0 0 10px 0; font-size: 18px;">${feedEmoji} ${feedName} 피드</h3>
          <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">더 많은 흥미로운 콘텐츠를 발견하세요</p>
          <a href="#" target="_blank" rel="noopener" onclick="console.log('${feedType} feed ad clicked')" 
             style="background: #fff; color: #667eea; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
            콘텐츠 탐색
          </a>
        </div>
      `;
    }
    
    return (
      <AdBanner 
        position="sidebar" 
        size="large" 
        section="feed" 
        className={className}
        customContent={adContent}
      />
    );
  }
}
