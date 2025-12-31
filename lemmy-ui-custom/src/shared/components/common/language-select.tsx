import { selectableLanguages } from "@utils/app";
import { randomStr } from "@utils/helpers";
import classNames from "classnames";
import { Component, linkEvent } from "inferno";
import { Language } from "lemmy-js-client";
import { I18NextService, UserService } from "../../services";
import { Icon } from "./icon";

interface LanguageSelectProps {
  allLanguages: Language[];
  siteLanguages: number[];
  selectedLanguageIds?: number[];
  multiple?: boolean;
  onChange(val: number[]): any;
  showAll?: boolean;
  showSite?: boolean;
  iconVersion?: boolean;
  disabled?: boolean;
  showLanguageWarning?: boolean;
}

export class LanguageSelect extends Component<LanguageSelectProps, any> {
  private id = `language-select-${randomStr()}`;

  constructor(props: any, context: any) {
    super(props, context);
  }

  componentDidMount() {
    this.setSelectedValues();
  }

  // Necessary because there is no HTML way to set selected for multiple in value=
  setSelectedValues() {
    const ids = this.props.selectedLanguageIds?.map(toString);
    if (ids) {
      const select = (document.getElementById(this.id) as HTMLSelectElement)
        .options;
      for (let i = 0; i < select.length; i++) {
        const o = select[i];
        if (ids.includes(o.value)) {
          o.selected = true;
        }
      }
    }
  }

  render() {
    return this.props.iconVersion ? (
      this.selectBtn
    ) : (
      <div className="language-select mb-3">
        <label
          className={classNames(
            "col-form-label",
            `col-sm-${this.props.multiple ? 3 : 2}`,
          )}
          htmlFor={this.id}
        >
          {I18NextService.i18n.t(
            this.props.multiple ? "language_plural" : "language",
          )}
        </label>
        {this.props.multiple && this.props.showLanguageWarning && (
          <div
            id="lang-warning"
            className="alert small alert-warning"
            role="alert"
          >
            <Icon icon="alert-triangle" classes="icon-inline me-2" />
            {I18NextService.i18n.t("undetermined_language_warning")}
          </div>
        )}
        <div
          className={classNames(`col-sm-${this.props.multiple ? 9 : 10}`, {
            "d-flex flex-column": this.props.multiple,
          })}
        >
          {this.props.multiple && (
            <div className="btn-group mb-2" role="group">
              <button
                type="button"
                className="btn btn-sm btn-outline-primary"
                onClick={linkEvent(this, this.handleSelectAll)}
              >
                <Icon icon="check-square" classes="icon-inline me-1" />
                {I18NextService.i18n.t("select_all")}
              </button>
              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                onClick={linkEvent(this, this.handleDeselectAll)}
              >
                <Icon icon="x" classes="icon-inline me-1" />
                {I18NextService.i18n.t("deselect_all")}
              </button>
            </div>
          )}
          {this.props.multiple ? this.checkboxList : this.selectBtn}
        </div>
      </div>
    );
  }

  get checkboxList() {
    const selectedLangs = this.props.selectedLanguageIds || [];
    const filteredLangs = selectableLanguages(
      this.props.allLanguages,
      this.props.siteLanguages,
      this.props.showAll,
      this.props.showSite,
      UserService.Instance.myUserInfo,
    );

    return (
      <div 
        className="language-checkbox-list border rounded p-2" 
        style={{ maxHeight: "300px", overflowY: "auto" }}
      >
        {filteredLangs.length === 0 ? (
          <div className="text-muted small">
            {I18NextService.i18n.t("no_languages_available")}
          </div>
        ) : (
          filteredLangs.map(l => (
            <div key={l.id} className="form-check">
              <input
                className="form-check-input"
                type="checkbox"
                id={`${this.id}-lang-${l.id}`}
                value={l.id}
                checked={selectedLangs.includes(l.id)}
                onChange={linkEvent(
                  { component: this, languageId: l.id },
                  this.handleCheckboxChange,
                )}
                disabled={this.props.disabled}
              />
              <label
                className="form-check-label"
                htmlFor={`${this.id}-lang-${l.id}`}
              >
                {l.name}
              </label>
            </div>
          ))
        )}
      </div>
    );
  }

  get selectBtn() {
    const selectedLangs = this.props.selectedLanguageIds;
    const filteredLangs = selectableLanguages(
      this.props.allLanguages,
      this.props.siteLanguages,
      this.props.showAll,
      this.props.showSite,
      UserService.Instance.myUserInfo,
    );

    return (
      <select
        className={classNames("form-select w-auto", {
          "d-inline-block": !this.props.iconVersion,
        })}
        id={this.id}
        onChange={linkEvent(this, this.handleLanguageChange)}
        aria-label={I18NextService.i18n.t("language_select_placeholder")}
        aria-describedby={
          this.props.multiple && this.props.showLanguageWarning
            ? "lang-warning"
            : ""
        }
        multiple={this.props.multiple}
        disabled={this.props.disabled}
      >
        {!this.props.multiple && (
          <option selected disabled hidden>
            {I18NextService.i18n.t("language_select_placeholder")}
          </option>
        )}
        {filteredLangs.map(l => (
          <option
            key={l.id}
            value={l.id}
            selected={selectedLangs?.includes(l.id)}
          >
            {l.name}
          </option>
        ))}
      </select>
    );
  }

  handleCheckboxChange(
    data: { component: LanguageSelect; languageId: number },
    event: any,
  ) {
    const { component, languageId } = data;
    const currentSelected = component.props.selectedLanguageIds || [];
    const isChecked = event.target.checked;

    let newSelected: number[];
    if (isChecked) {
      // Add language if not already selected
      newSelected = currentSelected.includes(languageId)
        ? currentSelected
        : [...currentSelected, languageId];
    } else {
      // Remove language
      newSelected = currentSelected.filter(id => id !== languageId);
    }

    component.props.onChange(newSelected);
  }

  handleLanguageChange(i: LanguageSelect, event: any) {
    const options: HTMLOptionElement[] = Array.from(event.target.options);
    const selected: number[] = options
      .filter(o => o.selected)
      .map(o => Number(o.value));

    i.props.onChange(selected);
  }

  handleSelectAll(i: LanguageSelect, event: any) {
    event.preventDefault();
    const filteredLangs = selectableLanguages(
      i.props.allLanguages,
      i.props.siteLanguages,
      i.props.showAll,
      i.props.showSite,
      UserService.Instance.myUserInfo,
    );
    const allLanguageIds = filteredLangs.map(l => l.id);
    i.props.onChange(allLanguageIds);
  }

  handleDeselectAll(i: LanguageSelect, event: any) {
    event.preventDefault();
    i.props.onChange([]);
  }
}
