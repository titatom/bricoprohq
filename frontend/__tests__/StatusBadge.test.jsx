import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import StatusBadge from '../components/StatusBadge';

describe('StatusBadge', () => {
  it('renders the status label with underscores replaced by spaces', () => {
    render(<StatusBadge status="needs_review" />);
    expect(screen.getByText('needs review')).toBeInTheDocument();
  });

  it('renders a dash when status is empty', () => {
    render(<StatusBadge status="" />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders a dash when status is undefined', () => {
    render(<StatusBadge status={undefined} />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('applies a green class for "active" status', () => {
    const { container } = render(<StatusBadge status="active" />);
    expect(container.firstChild.className).toContain('text-green-800');
  });

  it('applies a red class for "error" status', () => {
    const { container } = render(<StatusBadge status="error" />);
    expect(container.firstChild.className).toContain('text-red-700');
  });

  it('falls back to default grey for an unknown status', () => {
    const { container } = render(<StatusBadge status="unknown_xyz" />);
    expect(container.firstChild.className).toContain('text-gray-600');
    expect(screen.getByText('unknown xyz')).toBeInTheDocument();
  });
});
