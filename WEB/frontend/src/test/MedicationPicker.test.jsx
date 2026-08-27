import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import MedicationPicker from '../components/MedicationPicker';

/**
 * Reported from production: "typing calcium should show options".
 *
 * The field was a `<datalist>` fed from the PRESCRIPTION table. The account had
 * 943 dose logs and zero prescriptions, so typing "Calcium" offered nothing
 * while its own history held Calcium carbonate 489 times.
 */

const OPTIONS = [
  { name: 'Calcium carbonate', times_logged: 489, last_taken: '2026-08-24', source: 'logged' },
  { name: 'Calcitriol', times_logged: 351, last_taken: '2026-08-23', source: 'logged' },
  { name: 'Folic Acid', times_logged: 20, last_taken: '2026-05-31', source: 'logged' },
  { name: 'Lisinopril', source: 'prescription' },
];

function Harness({ initial = '' }) {
  const [v, setV] = require('react').useState(initial);
  return <MedicationPicker value={v} onChange={setV} options={OPTIONS} />;
}

const typeInto = (text) => {
  const input = screen.getByTestId('medication-picker-input');
  fireEvent.focus(input);
  fireEvent.change(input, { target: { value: text } });
  return input;
};

describe('MedicationPicker', () => {
  it('typing "calcium" shows the matching medications', () => {
    render(<Harness />);
    typeInto('calcium');
    expect(screen.getByTestId('medication-suggestions')).toBeInTheDocument();
    expect(screen.getByText('Calcium carbonate')).toBeInTheDocument();
  });

  it('matches case-insensitively and on a partial word', () => {
    render(<Harness />);
    typeInto('CALCI');
    // "Calcium carbonate" and "Calcitriol" both contain it.
    expect(screen.getByText('Calcium carbonate')).toBeInTheDocument();
    expect(screen.getByText('Calcitriol')).toBeInTheDocument();
  });

  it('matches a substring, not only a prefix', () => {
    render(<Harness />);
    typeInto('carbonate');
    expect(screen.getByText('Calcium carbonate')).toBeInTheDocument();
  });

  it('shows provenance so a real drug is distinguishable from a stray entry', () => {
    render(<Harness />);
    typeInto('calcium');
    expect(screen.getByText(/Taken 489×/)).toBeInTheDocument();
  });

  it('labels a prescription differently from a logged drug', () => {
    render(<Harness />);
    typeInto('lisin');
    expect(screen.getByText('On your prescription list')).toBeInTheDocument();
  });

  it('choosing a suggestion fills the field exactly', () => {
    render(<Harness />);
    typeInto('calcium');
    fireEvent.mouseDown(screen.getByText('Calcium carbonate'));
    expect(screen.getByTestId('medication-picker-input')).toHaveValue('Calcium carbonate');
  });

  it('keyboard selection works', () => {
    render(<Harness />);
    const input = typeInto('calci');
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(input.value).toMatch(/Calc/);
  });

  it('still accepts a drug that is not in history', () => {
    render(<Harness />);
    const input = typeInto('Brand New Drug');
    expect(input).toHaveValue('Brand New Drug');
    expect(screen.queryByTestId('medication-suggestions')).toBeNull();
  });

  it('a one-letter typo shows the real drug rather than nothing', () => {
    /** The production 422 was "Calcium Carbonated" — one letter off a drug
     *  logged 489 times. Choosing from the list cannot produce that. */
    render(<Harness />);
    typeInto('Calcium Carbonat');
    expect(screen.getByText('Calcium carbonate')).toBeInTheDocument();
  });
});
