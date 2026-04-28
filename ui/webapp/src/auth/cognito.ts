// Thin wrapper around amazon-cognito-identity-js.
//
// Manages a single signed-in CognitoUser, returns a fresh JWT on demand.
// Auto-refreshes via the SDK's built-in refresh token flow.

import {
  CognitoUser,
  CognitoUserPool,
  AuthenticationDetails,
  CognitoUserAttribute,
} from "amazon-cognito-identity-js";

const POOL = new CognitoUserPool({
  UserPoolId: __WORKQ_COGNITO_USER_POOL_ID__,
  ClientId: __WORKQ_COGNITO_CLIENT_ID__,
});

export class CognitoAuth {
  static instance = new CognitoAuth();

  currentUser(): CognitoUser | null {
    return POOL.getCurrentUser();
  }

  async signIn(email: string, password: string): Promise<void> {
    const user = new CognitoUser({ Username: email, Pool: POOL });
    const auth = new AuthenticationDetails({ Username: email, Password: password });
    return new Promise((resolve, reject) => {
      user.authenticateUser(auth, {
        onSuccess: () => resolve(),
        onFailure: (err) => reject(err),
        newPasswordRequired: () => reject(new Error("password change required — set in AWS Console")),
      });
    });
  }

  async signUp(email: string, password: string): Promise<void> {
    return new Promise((resolve, reject) => {
      POOL.signUp(
        email,
        password,
        [new CognitoUserAttribute({ Name: "email", Value: email })],
        [],
        (err) => {
          if (err) return reject(err);
          resolve();
        },
      );
    });
  }

  signOut(): void {
    const u = this.currentUser();
    if (u) u.signOut();
  }

  async getJwt(): Promise<string> {
    const u = this.currentUser();
    if (!u) throw new Error("not signed in");
    return new Promise((resolve, reject) => {
      u.getSession((err: Error | null, session: { isValid(): boolean; getAccessToken(): { getJwtToken(): string } } | null) => {
        if (err || !session) return reject(err ?? new Error("no session"));
        if (!session.isValid()) return reject(new Error("session invalid"));
        resolve(session.getAccessToken().getJwtToken());
      });
    });
  }

  async getEmail(): Promise<string> {
    const u = this.currentUser();
    if (!u) return "";
    return new Promise((resolve) => {
      u.getSession((err: Error | null) => {
        if (err) return resolve("");
        u.getUserAttributes((aerr, attrs) => {
          if (aerr || !attrs) return resolve("");
          const a = attrs.find((x) => x.getName() === "email");
          resolve(a?.getValue() ?? "");
        });
      });
    });
  }
}
