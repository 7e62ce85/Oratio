import { setIsoData } from "@utils/app";
import { Component } from "inferno";
import { GetSiteResponse } from "lemmy-js-client";
import { I18NextService } from "../../services";
import { HtmlTags } from "../common/html-tags";
import { Icon } from "../common/icon";

interface AboutTopic {
  icon: string;
  title: string;
  description: string;
}

interface AboutState {
  siteRes: GetSiteResponse;
}

// 8개 토픽 정의 - 필요에 따라 내용 수정 가능
const ABOUT_TOPICS: AboutTopic[] = [
  {
    icon: "globe",
    title: "Can I criticize the Jews here?",
    description: `Yes you can. Fuck Jews, they have a long history of killing their neighbors from Egypt and Bolshevist Russia to the Covid kill-shot and Palestine today.<br>Even their own bible is full of neighbor killing.<br>Jesus, a Jew himself, told them to love their neighbors and they killed him.`,
  },
  {
    icon: "shield",
    title: `Can I say "nigger" here?`,
    description: `Yes, you can nigger.`,
  },
  {
    icon: "user",
    title: "What can I NOT say?",
    description: `Child porn and abuse is not allowed here. Should you see some please report it.<br>(This does not include drawings, but does include realistic AI generated images.)<br><br>Violent or pornographic posts should be marked with the NSFW tag.`,
  },
  {
    icon: "message-square",
    title: "What is good about Oratio.space?",
    description: `Free speech (including questioning Jews) and easy to find information.<br><br>Strong stance against AI/bot slop and spam.`,
  },
  {
    icon: "code",
    title: "Won't Oratio.space just be shut down like all the other attempts?",
    description: `Oratio is hosted in a way that should be hard to shut down. It is anonymously hosted too.<br><br>In addition Oratio is <a href="https://github.com" target="_blank">open source</a> and we will share the database and back it up ourselves too.<br><br>This means that this site can never be permanently taken down.`,
  },
  {
    icon: "zap",
    title: "Is this a honeypot?",
    description: `No, unlike many other sites we do not require personal information or traceable payments.<br>We don't require phone numbers or even emails for registration.<br><br>We also do not block or frustrate the TOR browser like some websites do.<br><br>That said we still recommend posting via the TOR browser or at the least a VPN.<br>The TOR browser is not scary and can installed like any normal browser from here:<br><a href="https://www.torproject.org/download/" target="_blank">https://www.torproject.org/download/</a>`,
  },
  {
    icon: "flag",
    title: "How will you prevent AI and bot slop?",
    description: `We have two main lines of defense.<br><br>First of all posting will require proof of work. This will not be a problem for people, but can make bot posting prohibitively expensive.<br><br>Secondly we will give human badges to paid users and you will be able to filter to only see paid users.<br><br>Other defenses may be added on top of these in the future where appropriate.<br><br>While this will not be perfect our site should have a much better signal-to-noise ratio than sites that intentionally boost engagement numbers with bot activity.`,
  },
  {
    icon: "heart",
    title: "Why not use 4chan or upgoat.net?",
    description: `4chan has its charm, but it has a lot of noise and shilling.<br>This noise and shilling may be why it is allowed to stay up, but we believe we can do better.<br><br>We don't know who is behind Upgoat. It may be people from the old Voat/Poal forums ("goats") and they certainly have users from there.<br>However, we don't know and the site doesn't seem to have a viable business plan to stay online other than begging for donations.<br>Because of this upgoat could easily disappear one day with all your posts, discussions and contacts.<br><br>Our site will have modern features to find information and will be self-funded with ads and premium user memberships.`,
  },
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
                      <h5 className="card-title fw-semibold mb-2">{topic.title}</h5>
                      <p 
                        className="card-text text-muted mb-0"
                        dangerouslySetInnerHTML={{ __html: topic.description }}
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
