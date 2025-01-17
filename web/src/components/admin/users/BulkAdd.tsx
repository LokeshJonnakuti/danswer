"use client";
import useSWRMutation from "swr/mutation";
import { RobotIcon } from "@/components/icons/icons";
import { withFormik, FormikProps, FormikErrors, Form, Field } from "formik";

import { BackButton } from "@/components/BackButton";
import { Card } from "@tremor/react";
import { AdminPageTitle } from "@/components/admin/Title";
import { fetchAssistantEditorInfoSS } from "@/lib/assistants/fetchPersonaEditorInfoSS";
import { Button, Text } from "@tremor/react";

const WHITESPACE_SPLIT = /\s+/;
const EMAIL_REGEX = /[^@]+@[^.]+\.[^.]/;

const addUsers = async (url: string, { arg }: { arg: Array<string> }) => {
  return await fetch(url, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ emails: arg }),
  });
};

interface FormProps {
  onSuccess: () => void;
}

interface FormValues {
  emails: string;
}

const AddUserFormRenderer = ({
  touched,
  errors,
  isSubmitting,
}: FormikProps<FormValues>) => (
  <Form>
    <div className="flex flex-col gap-y-4">
      <Field id="emails" name="emails" as="textarea" className="p-4" />
      {touched.emails && errors.emails && (
        <div className="text-error text-sm">{errors.emails}</div>
      )}
      <Button
        className="mx-auto"
        color="green"
        size="md"
        type="submit"
        disabled={isSubmitting}
      >
        Add!
      </Button>
    </div>
  </Form>
);

const AddUserForm = withFormik<FormProps, FormValues>({
  mapPropsToValues: (props) => {
    return {
      emails: "",
    };
  },
  validate: (values: FormValues): FormikErrors<FormValues> => {
    const emails = values.emails.trim().split(WHITESPACE_SPLIT);
    if (!emails.some(Boolean)) {
      return { emails: "Required" };
    }
    for (let email of emails) {
      if (!email.match(EMAIL_REGEX)) {
        return { emails: `${email} is not a valid email` };
      }
    }
    return {};
  },
  handleSubmit: async (values: FormValues, formikBag) => {
    const emails = values.emails.trim().split(WHITESPACE_SPLIT);
    await addUsers("/api/manage/admin/users", { arg: emails }).then((res) => {
      if (res.ok) {
        formikBag.props.onSuccess();
      }
    });
  },
})(AddUserFormRenderer);

const BulkAdd = ({ onSuccess }: FormProps) => {
  return <AddUserForm onSuccess={onSuccess} />;
};

export default BulkAdd;
