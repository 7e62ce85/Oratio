import { Component, linkEvent } from "inferno";
import { I18NextService } from "../../services";
import { PaginationCursor } from "lemmy-js-client";

interface PaginatorCursorProps {
  nextPage?: PaginationCursor;
  onNext(val: PaginationCursor): void;
  onPrev?(): void;
  prevDisabled?: boolean;
}

function handleNext(i: PaginatorCursor) {
  if (i.props.nextPage) {
    i.props.onNext(i.props.nextPage);
  }
}

function handlePrev(i: PaginatorCursor) {
  if (i.props.onPrev) {
    i.props.onPrev();
  }
}

export class PaginatorCursor extends Component<PaginatorCursorProps, any> {
  constructor(props: any, context: any) {
    super(props, context);
  }
  render() {
    return (
      <div className="paginator my-2 d-flex gap-2">
        {this.props.onPrev && (
          <button
            className="btn btn-secondary"
            onClick={linkEvent(this, handlePrev)}
            disabled={this.props.prevDisabled}
          >
            {I18NextService.i18n.t("prev")}
          </button>
        )}
        <button
          className="btn btn-secondary"
          onClick={linkEvent(this, handleNext)}
          disabled={!this.props.nextPage}
        >
          {I18NextService.i18n.t("next")}
        </button>
      </div>
    );
  }
}
