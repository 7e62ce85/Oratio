import { Component } from "inferno";
import { AdBanner } from "../ad-banner";

interface CommunityAdProps {
  className?: string;
  customContent?: string;
  communityName?: string;
}

export class CommunityAd extends Component<CommunityAdProps, any> {
  render() {
    const { className = "", customContent, communityName } = this.props;
    
    // Community-specific ad content if no custom content provided
    let adContent = customContent;
    if (!adContent && communityName) {
      adContent = `
        <div style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); padding: 15px; border-radius: 8px; text-align: center; color: white; font-family: Arial, sans-serif;">
          <h3 style="margin: 0 0 10px 0; font-size: 18px;">👥 ${communityName} Community</h3>
          <p style="margin: 0 0 15px 0; font-size: 14px; opacity: 0.9;">Special offer for members of this community</p>
          <a href="#" target="_blank" rel="noopener" onclick="console.log('Community ${communityName} ad clicked')" 
             style="background: #fff; color: #fa709a; padding: 8px 20px; border-radius: 5px; text-decoration: none; font-weight: bold; display: inline-block;">
            Check Benefits
          </a>
        </div>
      `;
    }
    
    return (
      <AdBanner 
        position="sidebar" 
        size="medium" 
        section="community" 
        className={className}
        customContent={adContent}
      />
    );
  }
}
