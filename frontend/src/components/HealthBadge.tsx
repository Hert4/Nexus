import { useCallback, useEffect, useRef, useState } from 'react';
import { getHealth } from '../api/client';
import type { HealthResponse } from '../api/client';

type Indicator = 'ok' | 'degraded' | 'error';

const POLL_INTERVAL_MS = 30_000;

function statusToIndicator(health: HealthResponse): Indicator {
  return health.status === 'ok' ? 'ok' : 'degraded';
}

function indicatorLabel(s: Indicator): string {
  return s === 'ok' ? 'All systems operational' : s === 'degraded' ? 'Degraded' : 'Unreachable';
}

function serviceLabel(val: unknown): string {
  if (typeof val === 'string') return val;
  if (val && typeof val === 'object' && 'status' in val) {
    return (val as { status: string }).status;
  }
  return 'unknown';
}

export default function HealthBadge() {
  const [indicator, setIndicator] = useState<Indicator>('ok');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [showTooltip, setShowTooltip] = useState(false);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const poll = useCallback(async () => {
    try {
      const data = await getHealth();
      setHealth(data);
      setIndicator(statusToIndicator(data));
    } catch {
      setHealth(null);
      setIndicator('error');
    }
  }, []);

  useEffect(() => {
    void poll();
    const id = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [poll]);

  // Close tooltip when clicking outside
  useEffect(() => {
    if (!showTooltip) return;
    const handler = (e: MouseEvent) => {
      if (tooltipRef.current && !tooltipRef.current.contains(e.target as Node)) {
        setShowTooltip(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showTooltip]);

  return (
    <div className="health-badge" ref={tooltipRef}>
      <button
        className={`health-badge__dot health-badge__dot--${indicator}`}
        onClick={() => setShowTooltip((v) => !v)}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        aria-label={`API health: ${indicatorLabel(indicator)}`}
        title={indicatorLabel(indicator)}
      >
        <span className="visually-hidden">{indicatorLabel(indicator)}</span>
      </button>

      {showTooltip && (
        <div
          className="health-badge__tooltip"
          role="tooltip"
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
        >
          <p className="health-badge__tooltip-title">
            Backend — {indicatorLabel(indicator)}
          </p>
          {health ? (
            <ul className="health-badge__services">
              {Object.entries(health.services).map(([name, val]) => {
                const label = serviceLabel(val);
                return (
                  <li key={name} className={`health-badge__service health-badge__service--${label}`}>
                    <span className="health-badge__service-dot" />
                    <span className="health-badge__service-name">{name}</span>
                    <span className="health-badge__service-status">{label}</span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="health-badge__tooltip-error">Could not reach backend.</p>
          )}
        </div>
      )}
    </div>
  );
}
