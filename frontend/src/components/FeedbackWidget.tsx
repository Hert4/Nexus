import { useState } from 'react';
import { submitFeedback } from '../api/client';

interface FeedbackWidgetProps {
  messageId: string;
}

type SubmitState = 'idle' | 'submitting' | 'done' | 'error';

const STAR_LABELS = ['Terrible', 'Bad', 'OK', 'Good', 'Great'];

export default function FeedbackWidget({ messageId }: FeedbackWidgetProps) {
  const [hovered, setHovered] = useState<number>(0);
  const [selected, setSelected] = useState<number>(0);
  const [comment, setComment] = useState('');
  const [showComment, setShowComment] = useState(false);
  const [submitState, setSubmitState] = useState<SubmitState>('idle');

  if (submitState === 'done') {
    return (
      <div className="feedback feedback--done" aria-live="polite">
        ✓ Thanks for your feedback!
      </div>
    );
  }

  const handleStarClick = (rating: number) => {
    setSelected(rating);
    // Show comment box for low ratings (≤3) automatically
    setShowComment(rating <= 3);
  };

  const handleSubmit = async () => {
    if (!selected || submitState === 'submitting') return;
    setSubmitState('submitting');
    try {
      await submitFeedback(messageId, selected, comment || undefined);
      setSubmitState('done');
    } catch {
      setSubmitState('error');
    }
  };

  const displayRating = hovered || selected;

  return (
    <div className="feedback" aria-label="Rate this response">
      {/* Stars */}
      <div className="feedback__stars" role="group" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((star) => (
          <button
            key={star}
            className={`feedback__star ${displayRating >= star ? 'feedback__star--active' : ''}`}
            onClick={() => handleStarClick(star)}
            onMouseEnter={() => setHovered(star)}
            onMouseLeave={() => setHovered(0)}
            aria-label={`${star} star${star !== 1 ? 's' : ''} – ${STAR_LABELS[star - 1]}`}
            aria-pressed={selected === star}
            disabled={submitState === 'submitting'}
            title={STAR_LABELS[star - 1]}
          >
            ★
          </button>
        ))}
        {displayRating > 0 && (
          <span className="feedback__label" aria-live="polite">
            {STAR_LABELS[displayRating - 1]}
          </span>
        )}
      </div>

      {/* Comment area (shown after rating or manually toggled) */}
      {selected > 0 && (
        <div className="feedback__comment-area">
          {!showComment ? (
            <button
              className="feedback__comment-toggle"
              onClick={() => setShowComment(true)}
            >
              Add comment (optional)
            </button>
          ) : (
            <textarea
              className="feedback__comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Tell us more (optional)…"
              rows={2}
              aria-label="Feedback comment"
              disabled={submitState === 'submitting'}
            />
          )}

          <button
            className="feedback__submit"
            onClick={handleSubmit}
            disabled={submitState === 'submitting'}
            aria-busy={submitState === 'submitting'}
          >
            {submitState === 'submitting' ? (
              <>
                <span className="spinner spinner--sm" aria-hidden="true" />
                Submitting…
              </>
            ) : (
              'Submit'
            )}
          </button>

          {submitState === 'error' && (
            <span className="feedback__error" role="alert">
              ⚠️ Failed to submit. Try again.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
