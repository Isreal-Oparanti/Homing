import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";

export const DEMO_ENABLED = process.env.DEMO_LOGIN_ENABLED === "true";
export const GOOGLE_ENABLED = Boolean(
  process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET,
);

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
