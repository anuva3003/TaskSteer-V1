import React, { useState } from 'react';
import {
    createTheme,
    ThemeProvider,
    Box,
    Grid,
    Paper,
    Typography,
    TextField,
    Button,
    InputAdornment,
    useMediaQuery,
    Divider,
    CircularProgress,
    Stack,
    IconButton,
} from '@mui/material';
import { keyframes } from '@mui/system';
// FIX: Direct imports for MUI icons to resolve potential bundling issues.
// NOTE: You must run `npm install @mui/icons-material` in your terminal for these imports to work.
import Visibility from '@mui/icons-material/Visibility'; 
import VisibilityOff from '@mui/icons-material/VisibilityOff';

// Firebase Imports
import { initializeApp, getApps, getApp } from 'firebase/app';
import { 
    getAuth, 
    createUserWithEmailAndPassword, 
    signInWithEmailAndPassword, 
    GoogleAuthProvider, 
    signInWithPopup 
} from "firebase/auth";

// --- FIREBASE CONFIGURATION ---
// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyBPneX8HLvkg1z6fGpTKUDDFOFUJkdf-iA", // This appears to be a placeholder, replace with your actual key
  authDomain: "tasksteer.firebaseapp.com",
  projectId: "tasksteer",
  storageBucket: "tasksteer.appspot.com",
  messagingSenderId: "553442098430",
  appId: "1:553442098430:web:9a79768fe81bdd15a379af",
  measurementId: "G-WQ2MC2GJNS"
};

// Initialize Firebase App
const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
const auth = getAuth(app);


// --- SVG ICONS ---
const UserIcon = ({ color = '#8b949e' }) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
);
const EmailIcon = ({ color = '#8b949e' }) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
);
const PasswordIcon = ({ color = '#8b949e' }) => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
);
const GoogleIcon = () => (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 48 48"><path fill="#FFC107" d="M43.611,20.083H42V20H24v8h11.303c-1.649,4.657-6.08,8-11.303,8c-6.627,0-12-5.373-12-12s5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24s8.955,20,20,20s20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z"></path><path fill="#FF3D00" d="M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z"></path><path fill="#4CAF50" d="M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z"></path><path fill="#1976D2" d="M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.574l6.19,5.238C39.99,35.962,44,30.606,44,24C44,22.659,43.862,21.35,43.611,20.083z"></path></svg>
);

// --- ANIMATIONS ---
const fadeIn = keyframes`
  from {
    opacity: 0;
    transform: translateY(15px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

const glow = keyframes`
  0% { box-shadow: 0 0 5px #b39ddb; }
  50% { box-shadow: 0 0 20px #8e44ad, 0 0 30px #b39ddb; }
  100% { box-shadow: 0 0 5px #b39ddb; }
`;


// --- THEME ---
const theme = createTheme({
    palette: {
        mode: 'dark',
        primary: { main: '#b39ddb' },
        background: {
            default: '#121212',
            paper: 'rgba(18, 18, 18, 0.75)',
        },
        error: { main: '#f44336' },
    },
    typography: {
        fontFamily: "'Inter', 'Helvetica', 'Arial', sans-serif",
        h1: { fontSize: '2.5rem', fontWeight: 700 },
        h2: { fontSize: '1.0rem', fontWeight: 400, color: '#a0a0a0'},
        body1: { color: '#c9d1d9' },
        h4: { fontSize: '2rem', fontWeight: 'bold' },
    },
    components: {
        MuiTextField: {
            styleOverrides: {
                root: {
                    '& .MuiOutlinedInput-root': {
                        backgroundColor: 'rgba(255, 255, 255, 0.07)',
                        '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#b39ddb' },
                        '& .MuiOutlinedInput-notchedOutline': {
                             borderColor: 'rgba(255, 255, 255, 0.15)', 
                             transition: 'border-color 0.3s' 
                        },
                    },
                },
            },
        },
    },
});

// --- SUB-COMPONENTS (Moved outside App) ---
const LeftPanel = () => (
    <Box sx={{
        width: { xs: '100%', md: '50%' },
        p: { xs: 4, md: 6 },
        display: { xs: 'none', md: 'flex' },
        flexDirection: 'column', 
        justifyContent: 'center',
        alignItems: 'center', 
        textAlign: 'center',
        background: `radial-gradient(circle at top left, rgba(179, 157, 219, 0.1), transparent 40%), radial-gradient(circle at bottom right, rgba(80, 80, 150, 0.1), transparent 50%), #0d0d0d`,
        minHeight: { xs: '50vh', md: 'auto' }
    }}>
        <Box>
            <Typography variant="h4" gutterBottom sx={{color: '#fff', mb: 1}}>
                Navigate Your Workflow.
            </Typography>
            <Typography variant="body1" sx={{ maxWidth: 380, color: '#8b949e', mb: 4 }}>
                A clear path to productivity. TaskSteer provides the tools to bring your projects from vision to reality, seamlessly.
            </Typography>
            <Box component="img" src="/assets/Illustration.png" alt="Hero Illustration" sx={{
                width: '100%', 
                maxWidth: 420, 
                height: 'auto', 
                objectFit: 'contain',
                borderRadius: 2, 
                mt: 4, 
                boxShadow: '0 10px 40px rgba(139, 92, 246, 0.1)',
            }}/>
        </Box>
    </Box>
);

const AuthForm = ({ 
    isLoginView, 
    handleAuthAction, 
    handleGoogleSignIn, 
    error, 
    loading, 
    name, setName, 
    email, setEmail, 
    password, setPassword,
    setIsLoginView,
    setError
}) => {
    const [showPassword, setShowPassword] = useState(false);

    const handleClickShowPassword = () => setShowPassword((show) => !show);
    const handleMouseDownPassword = (event) => {
        event.preventDefault();
    };

    return (
        <Box sx={{
            width: { xs: '100%', md: '50%' },
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#121212',
            p: { xs: '1.5rem', sm: 4 },
            minHeight: '100vh',
            overflowY: 'auto'
        }}>
            <Stack
                sx={{
                    width: '100%',
                    maxWidth: 400,
                }}
                spacing={4}
            >
                <Stack spacing={1} alignItems="center">
                    <Box sx={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: '16px' }}>
                        <Box component="img" src="/assets/LOHO.png" alt="TaskSteer Logo" sx={{ width: 50, height: 50, objectFit: 'contain', borderRadius: '8px' }}/>
                        <Typography component="h1" variant="h1" sx={{ color: '#fff' }}>
                            TaskSteer
                        </Typography>
                    </Box>
                    <Typography component="h2" variant="h2" sx={{ textAlign: 'center' }}>
                        {isLoginView ? 'Welcome back! Ready to get started?' : 'Create an account to begin.'}
                    </Typography>
                </Stack>
                
                <Box component="form" onSubmit={handleAuthAction} sx={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                     {!isLoginView && (
                         <TextField required fullWidth id="name" label="Full Name" name="name"
                             autoComplete="name" autoFocus value={name} onChange={(e) => setName(e.target.value)}
                             InputProps={{ startAdornment: (<InputAdornment position="start"><UserIcon /></InputAdornment>) }}/>
                     )}
                    <TextField required fullWidth id="email" label="Email Address" name="email"
                        autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)}
                        InputProps={{ startAdornment: (<InputAdornment position="start"><EmailIcon /></InputAdornment>) }}/>
                    <TextField 
                        required 
                        fullWidth 
                        name="password" 
                        label="Password" 
                        type={showPassword ? 'text' : 'password'}
                        id="password" 
                        autoComplete="current-password" 
                        value={password} 
                        onChange={(e) => setPassword(e.target.value)}
                        InputProps={{ 
                            startAdornment: (<InputAdornment position="start"><PasswordIcon /></InputAdornment>),
                            endAdornment: (
                                <InputAdornment position="end">
                                    <IconButton
                                        aria-label="toggle password visibility"
                                        onClick={handleClickShowPassword}
                                        onMouseDown={handleMouseDownPassword}
                                        edge="end"
                                    >
                                        {showPassword ? <VisibilityOff /> : <Visibility />}
                                    </IconButton>
                                </InputAdornment>
                            )
                        }}/>

                    {error && <Typography color="error" variant="body2" sx={{ textAlign: 'center', mt: 1 }}>{error}</Typography>}
                    
                    <Box sx={{mt: 2}}>
                        <Button type="submit" fullWidth variant="contained" disabled={loading} sx={{ 
                            py: 1.5, 
                            background: 'linear-gradient(45deg, #8e44ad 30%, #b39ddb 90%)', 
                            boxShadow: '0 4px 15px rgba(179, 157, 219, 0.2)', 
                            transition: 'all 0.3s ease', 
                            '&:hover': { 
                                transform: 'translateY(-2px)', 
                                boxShadow: '0 6px 20px rgba(179, 157, 219, 0.4)',
                                animation: `${glow} 1.5s ease-in-out`
                            } 
                        }}>
                            {loading ? <CircularProgress size={24} color="inherit" /> : (isLoginView ? 'Login' : 'Create Account')}
                        </Button>
                        
                        <Divider sx={{ my: 3, color: '#8b949e' }}>OR</Divider>

                        <Button fullWidth variant="outlined" startIcon={<GoogleIcon />} onClick={handleGoogleSignIn} disabled={loading}
                            sx={{ py: 1.5, borderColor: 'rgba(255,255,255,0.23)', color: '#fff', '&:hover': {borderColor: '#b39ddb', backgroundColor: 'rgba(179, 157, 219, 0.1)'}}}>
                            Sign In with Google
                        </Button>
                    </Box>
                </Box>
                
                <Grid container justifyContent="center" sx={{mt: 'auto'}}>
                    {/* FIX: Removed the 'item' prop from the Grid component as it is deprecated in MUI v5 */}
                    <Grid> 
                        <Typography variant="body2" component="a" href="#" onClick={(e) => { e.preventDefault(); setIsLoginView(!isLoginView); setError('')}}
                            sx={{ color: 'primary.main', textDecoration: 'none', cursor: 'pointer', '&:hover': { textDecoration: 'underline'} }}>
                            {isLoginView ? "Don't have an account? Sign Up" : "Already have an account? Login"}
                        </Typography>
                    </Grid>
                </Grid>
            </Stack>
        </Box>
    );
}

// --- Main App Component ---
const App = () => {
    const [isLoginView, setIsLoginView] = useState(true);
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    // FIX: The 'import.meta.env' syntax is not compatible with the older "es2015" target environment
    // specified in your build configuration. This causes a build warning and makes the
    // environment variable undefined.
    // The PROPER fix is to update your build configuration (e.g., vite.config.js) to a modern target like 'esnext'.
    // As a temporary workaround in this code, we are hardcoding the URL.
    const BACKEND_URL = "http://localhost:8080";

    const handleAuthAction = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            let userCredential;
            if (isLoginView) {
                userCredential = await signInWithEmailAndPassword(auth, email, password);
            } else {
                userCredential = await createUserWithEmailAndPassword(auth, email, password);
            }

            const token = await userCredential.user.getIdToken();
            
            const response = await fetch(`${BACKEND_URL}/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token }),
                credentials: 'include',
                mode: 'cors', 
            });

            if (response.ok) {
                window.location.href = "http://127.0.0.1:5500/tasksteer-frontend/html/index.html";
            } else {
                const errorText = await response.text();
                console.error("Server rejected:", errorText);
                setError(`Server Error: ${errorText}`);
            }
        } catch (err) {
            const firebaseError = err;
            setError(firebaseError.message);
        } finally {
            setLoading(false);
        }
    };

    const handleGoogleSignIn = async () => {
        setLoading(true);
        setError('');
        try {
            const provider = new GoogleAuthProvider();
            const result = await signInWithPopup(auth, provider);
            const token = await result.user.getIdToken();

            const response = await fetch(`${BACKEND_URL}/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ token }),
                credentials: 'include',
                mode: 'cors',
            });

            if (response.ok) {
                window.location.href = "http://127.0.0.1:5500/tasksteer-frontend/html/index.html";
            } else {
                const errorText = await response.text();
                console.error("Server rejected:", errorText);
                setError(`Server Error: ${errorText}`);
            }
        } catch (err) {
            console.error("Google sign-in failed:", err.message);
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };
    
    return (
        <ThemeProvider theme={theme}>
            <Box sx={{
                display: 'flex',
                flexDirection: { xs: 'column', md: 'row' },
                height: '100vh',
                width: '100vw',
                overflow: 'hidden',
            }}>
                 <LeftPanel />
                 <AuthForm
                    isLoginView={isLoginView}
                    handleAuthAction={handleAuthAction}
                    handleGoogleSignIn={handleGoogleSignIn}
                    error={error}
                    loading={loading}
                    name={name}
                    setName={setName}
                    email={email}
                    setEmail={setEmail}
                    password={password}
                    setPassword={setPassword}
                    setIsLoginView={setIsLoginView}
                    setError={setError}
                 />
            </Box>
        </ThemeProvider>
    );
};

export default App;
