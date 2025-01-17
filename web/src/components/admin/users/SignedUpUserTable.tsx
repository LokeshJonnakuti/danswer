import { type User, UserStatus } from "@/lib/types";
import CenteredPageSelector from "./CenteredPageSelector";
import { type PageSelectorProps } from "@/components/PageSelector";
import { HidableSection } from "@/app/admin/assistants/HidableSection";
import { PopupSpec } from "@/components/admin/connectors/Popup";
import userMutationFetcher from "@/lib/admin/users/userMutationFetcher";
import useSWRMutation from "swr/mutation";
import {
  Table,
  TableHead,
  TableRow,
  TableHeaderCell,
  TableBody,
  TableCell,
  Button,
} from "@tremor/react";
import { PageSelector } from "@/components/PageSelector";

interface Props {
  users: Array<User>;
  setPopup: (spec: PopupSpec) => void;
  mutate: () => void;
}

const PromoterButton = ({
  user,
  promote,
  onSuccess,
  onError,
}: {
  user: User;
  promote: boolean;
  onSuccess: () => void;
  onError: (message: string) => void;
}) => {
  const { trigger, isMutating } = useSWRMutation(
    promote
      ? "/api/manage/promote-user-to-admin"
      : "/api/manage/demote-admin-to-basic",
    userMutationFetcher,
    { onSuccess, onError }
  );
  return (
    <Button
      className="w-min"
      onClick={() => trigger({ user_email: user.email })}
      disabled={isMutating}
    >
      {promote ? "Promote" : "Demote"} to {promote ? "Admin" : "Basic"} User
    </Button>
  );
};

const DeactivaterButton = ({
  user,
  deactivate,
  onSuccess,
  onError,
}: {
  user: User;
  deactivate: boolean;
  onSuccess: () => void;
  onError: (message: string) => void;
}) => {
  const { trigger, isMutating } = useSWRMutation(
    deactivate
      ? "/api/manage/admin/deactivate-user"
      : "/api/manage/admin/activate-user",
    userMutationFetcher,
    { onSuccess, onError }
  );
  return (
    <Button
      className="w-min"
      onClick={() => trigger({ user_email: user.email })}
      disabled={isMutating}
    >
      {deactivate ? "Deactivate" : "Activate"} Access
    </Button>
  );
};

const SignedUpUserTable = ({
  users,
  setPopup,
  currentPage,
  totalPages,
  onPageChange,
  mutate,
}: Props & PageSelectorProps) => {
  if (!users.length) return null;

  const onSuccess = (message: string) => {
    mutate();
    setPopup({
      message,
      type: "success",
    });
  };
  const onError = (message: string) => {
    setPopup({
      message,
      type: "error",
    });
  };
  const onPromotionSuccess = () => {
    onSuccess("User promoted to admin user!");
  };
  const onPromotionError = (errorMsg: string) => {
    onError(`Unable to promote user - ${errorMsg}`);
  };
  const onDemotionSuccess = () => {
    onSuccess("Admin demoted to basic user!");
  };
  const onDemotionError = (errorMsg: string) => {
    onError(`Unable to demote admin - ${errorMsg}`);
  };

  const onDeactivateSuccess = () => {
    mutate();
    setPopup({
      message: "User deactivated!",
      type: "success",
    });
  };
  const onDeactivateError = (errorMsg: string) => {
    setPopup({
      message: `Unable to deactivate user - ${errorMsg}`,
      type: "error",
    });
  };
  const onActivateSuccess = () => {
    mutate();
    setPopup({
      message: "User activate!",
      type: "success",
    });
  };
  const onActivateError = (errorMsg: string) => {
    setPopup({
      message: `Unable to activate user - ${errorMsg}`,
      type: "error",
    });
  };
  return (
    <HidableSection sectionTitle="Signed Up Users">
      <>
        {totalPages > 1 ? (
          <CenteredPageSelector
            currentPage={currentPage}
            totalPages={totalPages}
            onPageChange={onPageChange}
          />
        ) : null}
        <Table className="overflow-visible">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Email</TableHeaderCell>
              <TableHeaderCell>Role</TableHeaderCell>
              <TableHeaderCell>Status</TableHeaderCell>
              <TableHeaderCell>
                <div className="flex">
                  <div className="ml-auto">Actions</div>
                </div>
              </TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {users.map((user) => (
              <TableRow key={user.id}>
                <TableCell>{user.email}</TableCell>
                <TableCell>
                  <i>{user.role === "admin" ? "Admin" : "User"}</i>
                </TableCell>
                <TableCell>
                  <i>{user.status === "live" ? "Active" : "Inactive"}</i>
                </TableCell>
                <TableCell>
                  <div className="flex flex-col items-end gap-y-2">
                    <PromoterButton
                      user={user}
                      promote={user.role !== "admin"}
                      onSuccess={onPromotionSuccess}
                      onError={onPromotionError}
                    />
                    <DeactivaterButton
                      user={user}
                      deactivate={user.status === UserStatus.live}
                      onSuccess={onDeactivateSuccess}
                      onError={onDeactivateError}
                    />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </>
    </HidableSection>
  );
};

export default SignedUpUserTable;
