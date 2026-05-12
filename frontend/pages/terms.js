import Head from 'next/head';
import Link from 'next/link';

export default function Terms() {
  return (
    <>
      <Head>
        <title>Terms &amp; Conditions – Bricopro HQ</title>
        <meta name="description" content="Terms and Conditions for Bricopro HQ" />
      </Head>

      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-brand-600 text-white">
          <div className="max-w-4xl mx-auto px-6 py-6 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
              <img
                src="/logos/bricopro-mark.png"
                alt="Bricopro"
                className="h-8 w-8"
                onError={(e) => { e.currentTarget.src = '/logos/bricopro-mark.svg'; }}
              />
              <span className="font-bold text-lg tracking-tight">Bricopro HQ</span>
            </Link>
            <nav className="flex gap-4 text-sm">
              <Link href="/privacy-policy" className="hover:underline underline-offset-2 opacity-75 hover:opacity-90 transition-opacity">Privacy Policy</Link>
              <Link href="/terms" className="underline underline-offset-2 opacity-90">Terms &amp; Conditions</Link>
            </nav>
          </div>
        </header>

        {/* Content */}
        <main className="max-w-4xl mx-auto px-6 py-12">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8 md:p-12">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Terms &amp; Conditions</h1>
            <p className="text-sm text-gray-500 mb-8">Last updated: May 2026</p>

            <div className="prose prose-gray max-w-none space-y-8 text-gray-700 leading-relaxed">

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">1. Acceptance of Terms</h2>
                <p>
                  By accessing or using Bricopro HQ (&ldquo;the Platform&rdquo;, &ldquo;we&rdquo;, &ldquo;our&rdquo;, or &ldquo;us&rdquo;), you agree
                  to be bound by these Terms &amp; Conditions and our{' '}
                  <Link href="/privacy-policy" className="text-brand-600 hover:underline">Privacy Policy</Link>.
                  If you do not agree to these terms, you may not use the Platform.
                </p>
                <p className="mt-3">
                  These terms apply to all users of the Platform, including administrators and any team
                  members who access the Platform through your account.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">2. Description of Service</h2>
                <p>
                  Bricopro HQ is a business management platform for home improvement and renovation
                  professionals. It provides tools for campaign management, scheduling, KPI tracking,
                  social media publishing, and integration with third-party services including Meta
                  (Facebook &amp; Instagram), Google Calendar, Google Business Profile, and Jobber.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">3. Account Registration and Security</h2>
                <p>
                  You are responsible for maintaining the confidentiality of your account credentials.
                  You agree to notify us immediately of any unauthorized use of your account. We are
                  not liable for any loss or damage arising from unauthorized access resulting from
                  your failure to protect your credentials.
                </p>
                <p className="mt-3">
                  You must provide accurate information when creating your account and keep it up to date.
                  Accounts are for individual business use; sharing access credentials with unauthorized
                  parties is prohibited.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">4. Third-Party Integrations</h2>
                <p>
                  The Platform allows you to connect third-party services. By connecting an integration,
                  you authorize Bricopro HQ to interact with that service on your behalf using the
                  permissions you grant during the OAuth authorization flow.
                </p>
                <p className="mt-3">You acknowledge that:</p>
                <ul className="list-disc pl-6 space-y-1 mt-2">
                  <li>Third-party services are governed by their own terms of service and privacy policies.</li>
                  <li>We are not responsible for the availability, accuracy, or conduct of third-party services.</li>
                  <li>You are responsible for complying with the terms of any connected third-party platform, including Meta&rsquo;s Platform Policy and Google&rsquo;s API Services User Data Policy.</li>
                  <li>You may revoke any integration at any time from the Settings page.</li>
                </ul>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">5. Acceptable Use</h2>
                <p>You agree not to use the Platform to:</p>
                <ul className="list-disc pl-6 space-y-1 mt-2">
                  <li>Violate any applicable law or regulation</li>
                  <li>Publish content that is unlawful, defamatory, abusive, or fraudulent</li>
                  <li>Violate the policies of any connected third-party platform</li>
                  <li>Attempt to gain unauthorized access to any system or network</li>
                  <li>Interfere with or disrupt the Platform or its infrastructure</li>
                  <li>Reverse-engineer, decompile, or copy any part of the Platform</li>
                  <li>Use automated scripts or bots to access the Platform in a way that overburdens our systems</li>
                </ul>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">6. Content Ownership</h2>
                <p>
                  You retain ownership of all content you create, upload, or publish through the Platform.
                  By using the Platform, you grant us a limited, non-exclusive license to store and process
                  your content solely for the purpose of providing the service.
                </p>
                <p className="mt-3">
                  You are solely responsible for the content you publish through integrations. You represent
                  and warrant that you have all necessary rights to publish such content and that it does
                  not infringe any third-party intellectual property rights.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">7. Availability and Modifications</h2>
                <p>
                  We strive to maintain Platform availability but do not guarantee uninterrupted service.
                  Scheduled maintenance, third-party outages, or unforeseen issues may cause temporary
                  unavailability. We are not liable for losses arising from service interruptions.
                </p>
                <p className="mt-3">
                  We reserve the right to modify, suspend, or discontinue any part of the Platform at
                  any time with reasonable notice where practicable.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">8. Disclaimer of Warranties</h2>
                <p>
                  The Platform is provided &ldquo;as is&rdquo; and &ldquo;as available&rdquo; without warranties of any kind,
                  express or implied, including but not limited to warranties of merchantability, fitness
                  for a particular purpose, or non-infringement. We do not warrant that the Platform will
                  be error-free or that defects will be corrected.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">9. Limitation of Liability</h2>
                <p>
                  To the maximum extent permitted by law, Bricopro HQ and its operators shall not be
                  liable for any indirect, incidental, special, consequential, or punitive damages,
                  including lost profits, data loss, or business interruption, arising out of or in
                  connection with your use of the Platform, even if advised of the possibility of such
                  damages.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">10. Termination</h2>
                <p>
                  You may stop using the Platform at any time. We reserve the right to suspend or
                  terminate your access if you violate these Terms. Upon termination, your right to
                  use the Platform ceases immediately. Sections 6, 8, 9, and 11 survive termination.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">11. Governing Law</h2>
                <p>
                  These Terms are governed by and construed in accordance with applicable law.
                  Any disputes arising under these Terms shall be resolved through good-faith
                  negotiation, and if unresolved, submitted to the competent courts of the
                  jurisdiction where the Platform operator is established.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">12. Changes to These Terms</h2>
                <p>
                  We may update these Terms from time to time. Updated terms will be posted on this page
                  with a revised date. Your continued use of the Platform after changes are posted
                  constitutes acceptance of the revised Terms.
                </p>
              </section>

              <section>
                <h2 className="text-xl font-semibold text-gray-900 mb-3">13. Contact Us</h2>
                <p>For questions about these Terms, contact us at:</p>
                <div className="mt-3 p-4 bg-gray-50 rounded-lg border border-gray-200 text-sm">
                  <p className="font-medium text-gray-800">Bricopro HQ</p>
                  <p className="text-gray-600 mt-1">Email: <a href="mailto:legal@bricoprohq.com" className="text-brand-600 hover:underline">legal@bricoprohq.com</a></p>
                </div>
              </section>
            </div>
          </div>
        </main>

        {/* Footer */}
        <footer className="max-w-4xl mx-auto px-6 py-8 text-center text-sm text-gray-400">
          <p>
            &copy; {new Date().getFullYear()} Bricopro HQ &mdash;{' '}
            <Link href="/privacy-policy" className="hover:text-gray-600 transition-colors">Privacy Policy</Link>
            {' '}&middot;{' '}
            <Link href="/terms" className="hover:text-gray-600 transition-colors">Terms &amp; Conditions</Link>
          </p>
        </footer>
      </div>
    </>
  );
}
