/**
 * One avatar, used by every surface that shows a person.
 *
 * Before this, the clinician grid drew its own initials circle and nothing
 * else drew anything at all — so a photo added in Profile would have appeared
 * in exactly one place. Every caller passes the same props and gets the same
 * fallback ladder: photo → initials → "?".
 */

// Deterministic tint per person, so a card keeps its colour between loads and
// a grid stays scannable. Moved here from ClinicianDashboard.
const AVATAR_TINTS = ['#0ea5e9', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#6366f1'];

export const tintFor = (id) => AVATAR_TINTS[Math.abs(Number(id) || 0) % AVATAR_TINTS.length];

export const initialsOf = (name) => (name || '?')
  .split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('') || '?';

export default function Avatar({ src, name, id, size = 44, className = '', style = {} }) {
  const box = {
    width: size, height: size, borderRadius: '50%', flexShrink: 0,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    overflow: 'hidden', ...style,
  };

  if (src) {
    return (
      <img
        src={src}
        // A name, not "avatar" — a screen reader announcing "image" for every
        // person in a patient grid says nothing at all.
        alt={name ? `${name}` : 'Profile photo'}
        className={className}
        style={{ ...box, objectFit: 'cover' }}
      />
    );
  }

  return (
    <div
      className={className}
      // The initials are decorative when the name is already beside them;
      // the caller passes `name` for the cases where it is not.
      aria-hidden={!name ? undefined : 'true'}
      style={{
        ...box,
        background: tintFor(id), color: '#fff',
        fontWeight: 700, fontSize: Math.max(11, Math.round(size * 0.36)),
        lineHeight: 1, userSelect: 'none',
      }}
    >
      {initialsOf(name)}
    </div>
  );
}
