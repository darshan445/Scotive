class ApplicationMailer < ActionMailer::Base
  default from: ENV.fetch("DEVISE_MAILER_SENDER", "scotive@localhost")
  layout "mailer"
end
