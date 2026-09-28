// Minimal anchor fixture copied from the pinned SideStore SignInOperation shape.
// This intentionally keeps getAnisetteData private as in the pinned upstream:
// patch_sign_in_operation must fail closed if that declaration drifts.
final class SignInOperation {
    let skipCertificateProvisioning: Bool

    init(
        skipCertificateProvisioning: Bool = false
    ) throws {
        self.skipCertificateProvisioning = skipCertificateProvisioning
    }

    func execute() async throws {
        do {
            if var session = AuthManager.shared.session,
               let team = AuthManager.shared.team {
                _ = (session, team)
            }
        }
        let (account, session) = if let silentResult = try await self.silentSignIn() {
            silentResult
        } else {
            try await self.authenticationLoop()
        }
        _ = (account, session)
        do {
        } catch {
            if !AuthManager.shared.hasStoredPassword &&
               !AuthManager.shared.hasStoredXcodeToken
            {
                AuthManager.shared.signOut()
            }
        }
    }

    private func getAnisetteData() async throws -> ALTAnisetteData {
        try await AnisetteProvider.fetch(handler: self.anisetteServerHandler)
    }

    func authenticationLoop() async throws {
        while true {
            let (appleID, password) = try await handler.credentials()
            do {
                let (account, session) = try await signIn(appleID, password)
                await handler.handleSignInResult(.success((account, session)))
            } catch {
                self.debugLog("[SignInOperation] authenticationLoop: Attempt failed with error: \(error)")
                await handler.handleSignInResult(.failure(error))
            }
        }
    }
}
