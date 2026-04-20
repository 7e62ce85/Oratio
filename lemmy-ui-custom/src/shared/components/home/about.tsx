import { setIsoData } from "@utils/app";
import { Component } from "inferno";
import { GetSiteResponse } from "lemmy-js-client";
import { I18NextService } from "../../services";
import { HtmlTags } from "../common/html-tags";
import { Icon } from "../common/icon";

interface AboutTopic {
  icon: string;
  titleKey: string;
  descriptionKey: string;
}

interface AboutState {
  siteRes: GetSiteResponse;
}

// 8개 토픽 정의 - i18n 키 참조
const ABOUT_TOPICS: AboutTopic[] = [
  { icon: "globe", titleKey: "about_topic_1_title", descriptionKey: "about_topic_1_desc" },
  { icon: "shield", titleKey: "about_topic_2_title", descriptionKey: "about_topic_2_desc" },
  { icon: "user", titleKey: "about_topic_3_title", descriptionKey: "about_topic_3_desc" },
  { icon: "message-square", titleKey: "about_topic_4_title", descriptionKey: "about_topic_4_desc" },
  { icon: "code", titleKey: "about_topic_5_title", descriptionKey: "about_topic_5_desc" },
  { icon: "zap", titleKey: "about_topic_6_title", descriptionKey: "about_topic_6_desc" },
  { icon: "flag", titleKey: "about_topic_7_title", descriptionKey: "about_topic_7_desc" },
  { icon: "heart", titleKey: "about_topic_8_title", descriptionKey: "about_topic_8_desc" },
];

export class About extends Component<any, AboutState> {
  private isoData = setIsoData(this.context);
  state: AboutState = {
    siteRes: this.isoData.site_res,
  };

  constructor(props: any, context: any) {
    super(props, context);
  }

  get documentTitle(): string {
    return I18NextService.i18n.t("about");
  }

  render() {
    const site = this.state.siteRes.site_view.site;

    return (
      <div className="about container-lg py-4">
        <HtmlTags
          title={this.documentTitle}
          path={this.context.router.route.match.url}
        />
        
        {/* 헤더 섹션 */}
        <div className="text-center mb-5">
          <h1 className="display-5 fw-bold">{site.name}</h1>
          {site.description && (
            <p className="lead text-muted">{site.description}</p>
          )}
        </div>

        {/* 토픽 목록 (세로) */}
        <div className="row justify-content-center">
          <div className="col-12 col-lg-10">
            {ABOUT_TOPICS.map((topic, index) => (
              <div key={index} className="card border-0 shadow-sm mb-4">
                <div className="card-body">
                  <div className="d-flex align-items-start">
                    <span className="d-inline-flex align-items-center justify-content-center rounded-circle bg-primary bg-opacity-10 p-3 me-3 flex-shrink-0">
                      <Icon icon={topic.icon} classes="text-primary" />
                    </span>
                    <div>
                      <h5 className="card-title fw-semibold mb-2">{I18NextService.i18n.t(topic.titleKey)}</h5>
                      <p 
                        className="card-text text-muted mb-0"
                        dangerouslySetInnerHTML={{ __html: I18NextService.i18n.t(topic.descriptionKey) }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 푸터 섹션 */}
        <div className="text-center mt-5 pt-4 border-top">
          <p className="text-muted mb-0">
            oratio1809@proton.me
          </p>
        </div>
      </div>
    );
  }
}
