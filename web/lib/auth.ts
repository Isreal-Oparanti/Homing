import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";

export const DEMO_ENABLED = process.env.DEMO_LOGIN_ENABLED === "true";
export const GOOGLE_ENABLED = Boolean(
  process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET,
);

// Google sign-in for anyone when this is empty (each person gets their own account; the model
// budget caps each one and everyone together). A list (comma-separated) limits it to those emails.
const GOOGLE_ALLOWED = (process.env.GOOGLE_ALLOWED_EMAILS ?? "")
  .split(",")
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean);

const providers: NextAuthOptions["providers"] = [];

if (GOOGLE_ENABLED) {
  providers.push(
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  );
}

if (DEMO_ENABLED) {
  // One shared demo account with a seeded pile, so judges can try Homing without signing up.
  providers.push(
    CredentialsProvider({
      id: "demo",
      name: "Demo",
      credentials: {},
      async authorize() {
        return { id: "demo", email: "demo@homing.local", name: "Demo" };
      },
    }),
  );
}

export const authOptions: NextAuthOptions = {
  providers,
  session: { strategy: "jwt" },
  pages: { signIn: "/" },
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider !== "google" || GOOGLE_ALLOWED.length === 0) return true;
      return GOOGLE_ALLOWED.includes((user.email ?? "").toLowerCase());
    },
    async jwt({ token, user, account }) {
      if (user) {
        token.uid =
          account?.provider === "google" ? `google:${account.providerAccountId}` : user.id;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user && typeof token.uid === "string") {
        session.user.id = token.uid;
      }
      return session;
    },
  },
};
