import { Component } from "inferno";
import { AdBanner } from "../ad-banner";

interface HeaderAdProps {
  className?: string;
  customContent?: string;
}

export class HeaderAd extends Component<HeaderAdProps, any> {
  render() {
    const { className = "", customContent } = this.props;
    
    return (
      <AdBanner 
        position="header" 
        size="large" 
        section="general" 
        className={className}
        customContent={customContent}
      />
    );
  }
}
