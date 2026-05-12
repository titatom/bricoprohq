import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Mock useAuth before importing LoginForm
const mockLogin = jest.fn();
jest.mock('../context/AuthContext', () => ({
  useAuth: () => ({ login: mockLogin }),
}));

import LoginForm from '../components/LoginForm';

beforeEach(() => {
  mockLogin.mockReset();
});

describe('LoginForm', () => {
  it('renders email and password fields and a submit button', () => {
    render(<LoginForm />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('pre-fills the email field with the default admin address', () => {
    render(<LoginForm />);
    expect(screen.getByLabelText(/email/i)).toHaveValue('admin@bricopro.local');
  });

  it('calls login with the entered credentials on submit', async () => {
    mockLogin.mockResolvedValue({});
    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'user@example.com' } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith('user@example.com', 'secret'));
  });

  it('shows an error message when login throws', async () => {
    mockLogin.mockRejectedValue(new Error('Invalid credentials'));
    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() =>
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument()
    );
  });

  it('disables the submit button while signing in', async () => {
    let resolve;
    mockLogin.mockImplementation(() => new Promise((res) => { resolve = res; }));
    render(<LoginForm />);

    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'pw' } });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled();
    resolve({});
  });
});
