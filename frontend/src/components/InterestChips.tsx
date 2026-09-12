import { INTERESTS } from "../lib/format";

interface Props {
  selected: Set<string>;
  onToggle: (interest: string) => void;
}

export function InterestChips({ selected, onToggle }: Props) {
  return (
    <div className="chips">
      {INTERESTS.map((interest) => (
        <button
          key={interest}
          type="button"
          className="chip"
          aria-pressed={selected.has(interest)}
          onClick={() => onToggle(interest)}
        >
          {interest}
        </button>
      ))}
    </div>
  );
}
