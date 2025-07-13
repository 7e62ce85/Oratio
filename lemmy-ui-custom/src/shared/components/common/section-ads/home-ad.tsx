import { Component } from "inferno";
import { AdBanner } from "../ad-banner";

interface HomeAdProps {
  className?: string;
  customContent?: string;
}

export class HomeAd extends Component<HomeAdProps, any> {
  render() {
    const { className = "", customContent } = this.props;
    
    return (
      <AdBanner 
        position="sidebar" 
        size="medium" 
        section="home" 
        className={className}
        customContent={customContent}
      />
    );
  }
}
