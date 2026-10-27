/**
 * Forgot-password and reset-password pages. The Supabase client and the router are faked, so
 * no backend, email or network is needed.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import ForgotPassword from '../pages/forgot-password';
import ResetPassword from '../pages/reset-password';
import { supabase } from '../lib/supabaseClient';

const mockPush = jest.fn();
jest.mock('next/router', () => ({ useRouter: () => ({ push: mockPush }) }));

jest.mock('../lib/supabaseClient', () => ({
  supabase: {
    auth: {
      resetPasswordForEmail: jest.fn(),
      updateUser: jest.fn(),
      getSession: jest.fn(),
      onAuthStateChange: jest.fn(() => ({ data: { subscription: { unsubscribe: jest.fn() } } })),
    },
  },
}));

afterEach(() => {
  jest.clearAllMocks();
  window.location.hash = '';
});

test('forgot password sends the reset email with a link back to /reset-password', async () => {
  supabase.auth.resetPasswordForEmail.mockResolvedValue({ error: null });
  render(<ForgotPassword />);

  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

  expect(await screen.findByText(/a password reset link is on its way/)).toHaveClass('info');
  expect(supabase.auth.resetPasswordForEmail).toHaveBeenCalledWith('user@example.com', {
    redirectTo: `${window.location.origin}/reset-password`,
  });
});

test('forgot password shows a readable error when Supabase returns "{}"', async () => {
  supabase.auth.resetPasswordForEmail.mockResolvedValue({ error: { message: '{}' } });
  render(<ForgotPassword />);

  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

  expect(await screen.findByText(/Could not send the reset email/)).toHaveClass('error');
});

test('reset password saves the new password and goes to the dashboard', async () => {
  supabase.auth.getSession.mockResolvedValue({ data: { session: { access_token: 'recovery' } } });
  supabase.auth.updateUser.mockResolvedValue({ error: null });
  render(<ResetPassword />);

  fireEvent.change(await screen.findByLabelText('New password'), { target: { value: 'newpass123' } });
  fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'newpass123' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save new password' }));

  await screen.findByRole('button', { name: 'Save new password' });
  expect(supabase.auth.updateUser).toHaveBeenCalledWith({ password: 'newpass123' });
  expect(mockPush).toHaveBeenCalledWith('/dashboard');
});

test('reset password refuses mismatched passwords without calling Supabase', async () => {
  supabase.auth.getSession.mockResolvedValue({ data: { session: { access_token: 'recovery' } } });
  render(<ResetPassword />);

  fireEvent.change(await screen.findByLabelText('New password'), { target: { value: 'newpass123' } });
  fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'different1' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save new password' }));

  expect(await screen.findByText('The two passwords do not match.')).toHaveClass('error');
  expect(supabase.auth.updateUser).not.toHaveBeenCalled();
});

test('an expired reset link offers to send a new one', async () => {
  window.location.hash = '#error=access_denied&error_code=otp_expired';
  render(<ResetPassword />);

  expect(await screen.findByText(/invalid or has expired/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Send a new reset link' })).toHaveAttribute('href', '/forgot-password');
});

test('opening /reset-password without a link or session shows the expired message', async () => {
  supabase.auth.getSession.mockResolvedValue({ data: { session: null } });
  render(<ResetPassword />);

  expect(await screen.findByText(/invalid or has expired/)).toBeInTheDocument();
});
