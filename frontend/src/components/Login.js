import React, { useState } from 'react';
import axios from 'axios';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { toast } from 'sonner';

function Login({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [resetToken, setResetToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [resetPasswordMode, setResetPasswordMode] = useState(false);
  const [receivedToken, setReceivedToken] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await axios.post('/auth/login', { email, password });
      
      if (response.data.token && response.data.user) {
        localStorage.setItem('token', response.data.token);
        onLogin(response.data.user, response.data.token);
        toast.success('Logged in successfully!');
      }
    } catch (err) {
      console.error('Login error:', err);
      console.error('Error response:', err.response);
      console.error('Error message:', err.message);
      console.error('Request URL:', err.config?.url);
      
      let errorMessage = 'Authentication failed. Please try again.';
      
      if (err.code === 'ECONNREFUSED' || err.message.includes('Network Error')) {
        errorMessage = 'Cannot connect to server. Please make sure the backend is running on port 5001.';
      } else if (err.response?.status === 401) {
        errorMessage = err.response?.data?.error || 'Invalid email or password.';
      } else if (err.response?.status === 500) {
        errorMessage = 'Server error. Please try again later.';
      } else if (err.response?.data?.error) {
        errorMessage = err.response.data.error;
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    if (!email) {
      setError('Email is required');
      toast.error('Please enter your email address');
      setLoading(false);
      return;
    }

    try {
      console.log('Requesting password reset for:', email);
      const response = await axios.post('/auth/forgot-password', { email });
      console.log('Password reset response:', response.data);
      
      // If token is returned (for testing), show it
      if (response.data.token) {
        const token = response.data.token;
        setReceivedToken(token);
        setResetToken(token);
        setResetPasswordMode(true);
        toast.success('Reset token generated! Check the form below.');
        console.log('Reset token:', token); // Also log to console
      } else {
        const message = response.data.message || 'Check your email for reset instructions';
        toast.success(message);
        console.log('Password reset email sent:', message);
      }
    } catch (err) {
      console.error('Forgot password error:', err);
      console.error('Error response:', err.response?.data);
      const errorMessage = err.response?.data?.error || err.message || 'Failed to request password reset';
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    if (!resetToken || !newPassword) {
      setError('Token and password are required');
      setLoading(false);
      return;
    }

    try {
      const response = await axios.post('/auth/reset-password', {
        token: resetToken.trim(),
        password: newPassword
      });
      toast.success(response.data.message || 'Password reset successfully');
      // Return to login
      setResetPasswordMode(false);
      setResetToken('');
      setNewPassword('');
      setReceivedToken('');
    } catch (err) {
      const errorMessage = err.response?.data?.error || err.message || 'Failed to reset password';
      setError(errorMessage);
      toast.error(errorMessage);
      console.error('Reset password error:', err.response?.data || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div 
      className="min-h-screen flex items-center justify-center p-4 bg-white"
    >
      <Card className="w-full max-w-md shadow-lg border border-gray-200 bg-white">
        <CardHeader className="space-y-4 pb-8 pt-10">
          <div className="text-center space-y-2">
            <CardTitle className="text-3xl font-bold" style={{ color: '#5D98D1' }}>
              Cin7 Uploader
            </CardTitle>
            <CardDescription className="text-base text-slate-600 mt-3">
              Sales Order Upload Tool
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="space-y-6 pb-10">
          {resetPasswordMode ? (
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="reset-token">Reset Token</Label>
                <Input
                  id="reset-token"
                  type="text"
                  value={resetToken}
                  onChange={(e) => setResetToken(e.target.value)}
                  placeholder="Enter reset token"
                  required
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="new-password">New Password</Label>
                <Input
                  id="new-password"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="At least 6 characters"
                  required
                  minLength={6}
                  autoComplete="new-password"
                />
              </div>
              
              {error && (
                <div className="text-sm text-red-600 bg-red-50 border border-red-200 p-3 rounded-lg">
                  {error}
                </div>
              )}
              
              {resetToken && (
                <div className="text-xs bg-blue-50 border border-blue-200 p-2 rounded-lg">
                  <div className="font-semibold text-blue-800 mb-1">Token pre-filled:</div>
                  <div className="font-mono text-xs break-all text-blue-700">{resetToken.substring(0, 40)}...</div>
                </div>
              )}
              
              <div className="flex gap-2">
                <Button 
                  type="button"
                  variant="outline"
                  className="flex-1"
                  onClick={() => {
                    setResetPasswordMode(false);
                    setResetToken('');
                    setNewPassword('');
                    setError('');
                    setReceivedToken('');
                    setShowForgotPassword(false);
                  }}
                >
                  Cancel
                </Button>
                <Button 
                  type="submit" 
                  className="flex-1" 
                  disabled={loading}
                >
                  {loading ? 'Resetting...' : 'Reset Password'}
                </Button>
              </div>
            </form>
          ) : showForgotPassword ? (
            <form onSubmit={handleForgotPassword} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="forgot-email">Email</Label>
                <Input
                  id="forgot-email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  required
                  autoComplete="email"
                />
              </div>
              
              {error && (
                <div className="text-sm text-red-600 bg-red-50 border border-red-200 p-3 rounded-lg">
                  {error}
                </div>
              )}
              
              {receivedToken && (
                <div className="text-xs bg-green-50 border border-green-200 p-3 rounded-lg space-y-2">
                  <div className="font-semibold text-green-800">Reset token generated:</div>
                  <div className="font-mono text-xs break-all text-green-700 bg-white p-2 rounded border">
                    {receivedToken}
                  </div>
                  <div className="text-green-600">The token has been pre-filled below. Use it to reset your password.</div>
                </div>
              )}
              
              <Button 
                type="submit" 
                className="w-full" 
                disabled={loading}
              >
                {loading ? 'Requesting...' : 'Request Reset Token'}
              </Button>
              
              <Button 
                type="button"
                variant="ghost"
                className="w-full"
                onClick={() => {
                  setShowForgotPassword(false);
                  setError('');
                  setReceivedToken('');
                }}
              >
                Back to Login
              </Button>
            </form>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  required
                  autoComplete="email"
                />
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Your password"
                  required
                  autoComplete="current-password"
                />
              </div>
              
              {error && (
                <div className="text-sm text-red-600 bg-red-50 border border-red-200 p-3 rounded-lg">
                  {error}
                </div>
              )}
              
              <Button 
                type="submit" 
                className="w-full" 
                disabled={loading}
              >
                {loading ? 'Please wait...' : 'Sign In'}
              </Button>
              
              <div className="text-center">
                <button
                  type="button"
                  onClick={() => {
                    setShowForgotPassword(true);
                    setError('');
                  }}
                  className="text-sm text-primary hover:underline"
                >
                  Forgot password?
                </button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default Login;



